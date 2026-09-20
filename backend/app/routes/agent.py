"""AI agent endpoints.

POST /agent/chat    - talk to the fleet operations assistant
POST /agent/confirm - execute a previously-requested write action

Authentication is required for both (via get_current_user, same as every
other protected route in this app). Authorization for write actions is
enforced independently of anything the LLM decides — see
backend/app/agent/agent.py and the ownership/role checks in `confirm`
below.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.agent.agent import run_chat
from backend.app.agent.confirmations import pop_confirmation
from backend.app.agent.exceptions import AgentError, LLMProviderError, MaxToolCallsExceededError
from backend.app.agent.history import clear_history, get_history, save_history
from backend.app.agent.llm_client import LLMClient
from backend.app.agent.schemas import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse
from backend.app.agent.tools import ToolContext, send_robot_command
from backend.app.auth import ROLE_ADMIN, ROLE_OPERATOR, get_current_user
from backend.app.cache import redis_client
from backend.app.database import get_db
from backend.app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger("backend.app.agent")

RATE_LIMIT_MAX_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60


def _enforce_rate_limit(user: User) -> None:
    """Fixed-window rate limit using the app's existing Redis client.

    Deliberately not a second caching system — same redis_client instance
    everything else in the app already uses.
    """
    key = f"agent:ratelimit:{user.id}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)

    if count > RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many agent requests. Please wait a moment and try again.",
        )


def get_llm_client() -> LLMClient:
    """FastAPI dependency, overridden in tests with a fake client."""
    try:
        return LLMClient()
    except LLMProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
):
    _enforce_rate_limit(current_user)

    logger.info("agent.chat.request", extra={"user_id": current_user.id, "role": current_user.role})

    history = get_history(current_user.id)

    try:
        result = run_chat(
            db=db,
            current_user=current_user,
            message=request.message,
            llm_client=llm_client,
            history=history,
        )
    except MaxToolCallsExceededError:
        logger.warning("agent.chat.max_tool_calls", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This request required too many steps to answer safely. Try asking something narrower.",
        )
    except LLMProviderError:
        logger.error("agent.chat.llm_error", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is currently unavailable.",
        )
    except AgentError as exc:
        logger.error("agent.chat.error", extra={"user_id": current_user.id, "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The assistant could not complete that request."
        )

    save_history(current_user.id, result.messages)
    return result.response


@router.delete("/chat", status_code=status.HTTP_204_NO_CONTENT)
def reset_chat(current_user: User = Depends(get_current_user)):
    """Start a fresh conversation — clears this user's stored history only."""
    clear_history(current_user.id)


@router.post("/confirm", response_model=ConfirmResponse)
def confirm(
    request: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _enforce_rate_limit(current_user)

    pending = pop_confirmation(request.confirmation_id)

    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This confirmation is invalid or has expired.",
        )

    if pending["user_id"] != current_user.id:
        logger.warning(
            "agent.confirmation.ownership_mismatch",
            extra={"user_id": current_user.id, "confirmation_owner": pending["user_id"]},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This confirmation does not belong to you."
        )

    if current_user.role not in (ROLE_OPERATOR, ROLE_ADMIN):
        logger.warning(
            "agent.confirmation.role_revoked",
            extra={"user_id": current_user.id, "role": current_user.role},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You no longer have permission to send robot commands.",
        )

    ctx = ToolContext(db=db, current_user=current_user)

    try:
        result = send_robot_command(ctx, robot_id=pending["robot_id"], command=pending["command"])
    except Exception:
        logger.error(
            "agent.confirmation.execution_failed",
            extra={
                "user_id": current_user.id,
                "robot_id": pending["robot_id"],
                "command": pending["command"],
            },
        )
        return ConfirmResponse(
            response=f"Could not send '{pending['command']}' to {pending['robot_id']}. The command was not applied.",
            success=False,
            robot_id=pending["robot_id"],
            command=pending["command"],
        )

    logger.info(
        "agent.confirmation.executed",
        extra={
            "user_id": current_user.id,
            "robot_id": result.robot_id,
            "command": result.command,
            "confirmation_id": request.confirmation_id,
        },
    )

    return ConfirmResponse(
        response=f"Done — {result.robot_id} received '{result.command}' and is now {result.new_status}.",
        success=True,
        robot_id=result.robot_id,
        command=result.command,
    )
