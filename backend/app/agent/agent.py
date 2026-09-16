"""Agent orchestration: the tool-calling loop.

This is the only place that talks to the LLM client and decides what to do
with its output. It does not query the database directly — all data access
goes through backend.app.agent.tools, called via the ToolContext.

The critical security property enforced here (not by the LLM): a "write"
classified tool is NEVER executed from this loop. When the model asks for
one, this function validates the request, creates a pending confirmation in
Redis (backend.app.agent.confirmations), and returns immediately with
requires_confirmation=True. Only backend.app.routes.agent's /agent/confirm
endpoint — after independently re-checking identity, ownership, expiration,
and role — ever calls the write tool's underlying function.
"""

import json
import logging
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.agent.confirmations import create_confirmation
from backend.app.agent.exceptions import (
    MaxToolCallsExceededError,
    RobotNotFoundError,
    ToolNotFoundError,
)
from backend.app.agent.llm_client import LLMClient
from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.schemas import ChatResponse, SendRobotCommandArgs, ToolCallRecord
from backend.app.agent.tools import ToolContext, get_tool, tool_specs_for_llm
from backend.app.auth import ROLE_ADMIN, ROLE_OPERATOR
from backend.app.models.robot import Robot
from backend.app.models.user import User
from backend.app.routes.robots import COMMAND_STATUS

logger = logging.getLogger("backend.app.agent")

MAX_TOOL_CALLS = 8
WRITE_ALLOWED_ROLES = (ROLE_OPERATOR, ROLE_ADMIN)


@dataclass
class ChatRunResult:
    response: ChatResponse
    # The full provider-format transcript, for the route to persist as this
    # user's conversation history. Kept out of ChatResponse (the API-facing
    # model) since raw tool_use/tool_result content blocks are an internal,
    # provider-specific detail — not something to expose over the wire.
    messages: list[dict]


def _role_may_use(classification: str, role: str) -> bool:
    if classification == "write":
        return role in WRITE_ALLOWED_ROLES
    return True  # any authenticated role may use read tools


def _tool_result_block(tool_use_id: str, content: str, is_error: bool = False) -> dict:
    block: dict = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


def _serialize(result) -> str:
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    return json.dumps(result)


def run_chat(
    *,
    db: Session,
    current_user: User,
    message: str,
    llm_client: LLMClient,
    history: list[dict] | None = None,
) -> ChatRunResult:
    ctx = ToolContext(db=db, current_user=current_user)
    tool_call_records: list[ToolCallRecord] = []
    messages: list[dict] = [*(history or []), {"role": "user", "content": message}]

    for _ in range(MAX_TOOL_CALLS):
        turn = llm_client.generate_with_tools(
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tool_specs_for_llm(),
        )

        if not turn.tool_calls:
            messages.append({"role": "assistant", "content": turn.raw_content})
            response = ChatResponse(
                response=turn.text or "",
                tool_calls=tool_call_records,
                requires_confirmation=False,
                confirmation_id=None,
            )
            return ChatRunResult(response=response, messages=messages)

        messages.append({"role": "assistant", "content": turn.raw_content})

        tool_results: list[dict] = []
        confirmation_response: ChatResponse | None = None

        for call in turn.tool_calls:
            if confirmation_response is not None:
                # A write action earlier in this same turn already produced
                # a pending confirmation. Any further tool calls in this
                # turn are not executed, but every tool_use still needs a
                # paired tool_result or the next request's transcript would
                # be malformed.
                tool_results.append(
                    _tool_result_block(
                        call.id,
                        "Skipped: a different action in this turn is awaiting confirmation.",
                        is_error=True,
                    )
                )
                continue

            try:
                spec = get_tool(call.name)
            except ToolNotFoundError as exc:
                tool_call_records.append(ToolCallRecord(tool=call.name, status="error", detail=str(exc)))
                tool_results.append(_tool_result_block(call.id, f"Error: {exc}", is_error=True))
                continue

            if not _role_may_use(spec.classification, current_user.role):
                detail = f"Role '{current_user.role}' is not permitted to use '{spec.name}'."
                logger.info(
                    "agent.tool.permission_denied",
                    extra={"user_id": current_user.id, "role": current_user.role, "tool": spec.name},
                )
                tool_call_records.append(ToolCallRecord(tool=spec.name, status="error", detail=detail))
                tool_results.append(_tool_result_block(call.id, f"Error: {detail}", is_error=True))
                continue

            if spec.classification == "write":
                error = _validate_write_request(db, call.arguments)
                if error is not None:
                    tool_call_records.append(ToolCallRecord(tool=spec.name, status="error", detail=error))
                    tool_results.append(_tool_result_block(call.id, f"Error: {error}", is_error=True))
                    continue

                args = SendRobotCommandArgs.model_validate(call.arguments)
                confirmation_id = create_confirmation(
                    user_id=current_user.id,
                    username=current_user.username,
                    robot_id=args.robot_id,
                    command=args.command,
                )

                logger.info(
                    "agent.confirmation.created",
                    extra={
                        "user_id": current_user.id,
                        "robot_id": args.robot_id,
                        "command": args.command,
                        "confirmation_id": confirmation_id,
                    },
                )

                tool_call_records.append(ToolCallRecord(tool=spec.name, status="success"))
                tool_results.append(
                    _tool_result_block(call.id, "Pending user confirmation via the confirmation flow.")
                )

                message_text = turn.text or (
                    f"Sending '{args.command}' to {args.robot_id} will change its state. "
                    "Please confirm to proceed."
                )

                confirmation_response = ChatResponse(
                    response=message_text,
                    tool_calls=tool_call_records,
                    requires_confirmation=True,
                    confirmation_id=confirmation_id,
                )
                continue

            try:
                result = spec.func(ctx, **call.arguments)
                tool_call_records.append(ToolCallRecord(tool=spec.name, status="success"))
                tool_results.append(_tool_result_block(call.id, _serialize(result)))
            except RobotNotFoundError as exc:
                tool_call_records.append(ToolCallRecord(tool=spec.name, status="error", detail=str(exc)))
                tool_results.append(_tool_result_block(call.id, f"Error: {exc}", is_error=True))
            except (ValidationError, ValueError, TypeError) as exc:
                detail = f"Invalid arguments for '{spec.name}': {exc}"
                tool_call_records.append(ToolCallRecord(tool=spec.name, status="error", detail=detail))
                tool_results.append(_tool_result_block(call.id, f"Error: {detail}", is_error=True))

        messages.append({"role": "user", "content": tool_results})

        if confirmation_response is not None:
            return ChatRunResult(response=confirmation_response, messages=messages)

    raise MaxToolCallsExceededError(f"Exceeded the maximum of {MAX_TOOL_CALLS} tool calls for this request.")


def _validate_write_request(db: Session, raw_arguments: dict) -> str | None:
    """Return a human-readable error, or None if the write request is valid.

    Checked here — before ever creating a confirmation — so an invalid
    robot_id or unsupported command never produces a pending action at all
    (there is nothing for a confirmation to protect if it could never
    succeed).
    """
    try:
        args = SendRobotCommandArgs.model_validate(raw_arguments)
    except ValidationError as exc:
        return f"Invalid command request: {exc}"

    if db.get(Robot, args.robot_id) is None:
        return f"Robot '{args.robot_id}' not found."

    if args.command not in COMMAND_STATUS:
        return f"Unsupported command '{args.command}'. Supported commands: {sorted(COMMAND_STATUS)}."

    return None
