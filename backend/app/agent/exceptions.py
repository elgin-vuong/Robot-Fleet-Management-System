"""Agent-layer exceptions.

These are caught at the API boundary (backend/app/routes/agent.py) and turned
into safe, structured error responses. None of these should ever leak a raw
stack trace or internal detail to the client — see backend/app/routes/agent.py
for the mapping to HTTP status codes.
"""


class AgentError(Exception):
    """Base class for all agent-layer errors."""


class ToolNotFoundError(AgentError):
    """The LLM asked for a tool name that isn't registered."""


class ToolValidationError(AgentError):
    """Tool arguments failed validation (bad shape, out-of-range limit, etc.)."""


class ToolPermissionError(AgentError):
    """The authenticated user's role does not permit this tool."""


class RobotNotFoundError(AgentError):
    """The referenced robot_id does not exist."""

    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        super().__init__(f"Robot '{robot_id}' not found")


class ConfirmationError(AgentError):
    """Base class for confirmation-flow failures."""


class ConfirmationNotFoundError(ConfirmationError):
    """The confirmation_id does not exist, already expired, or was already used."""


class ConfirmationOwnershipError(ConfirmationError):
    """The confirmation exists but belongs to a different authenticated user."""


class MaxToolCallsExceededError(AgentError):
    """The tool-calling loop hit MAX_TOOL_CALLS without reaching a final answer."""


class LLMProviderError(AgentError):
    """The underlying LLM provider failed, timed out, or is not configured."""


class EmbeddingProviderError(AgentError):
    """The underlying embeddings provider failed, timed out, or is not configured."""
