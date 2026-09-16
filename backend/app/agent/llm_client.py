"""LLM provider abstraction.

This is the only file in the codebase that imports the `anthropic` SDK.
Everything else (agent.py, routes/agent.py) talks to `LLMClient`, so
swapping providers later means changing this one file, not scattering
provider-specific code through the orchestration layer.

Configuration is via environment variables only:
    AI_API_KEY   - required to actually call the provider
    AI_MODEL     - optional, defaults to DEFAULT_MODEL

No key is ever hard-coded, logged, or included in error messages sent to
clients.
"""

import os
from dataclasses import dataclass, field
from typing import Any

import anthropic

from backend.app.agent.exceptions import LLMProviderError

DEFAULT_MODEL = "claude-sonnet-5"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMTurnResult:
    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str
    # The raw assistant-turn content blocks, in the shape the provider
    # expects to see them echoed back as the "assistant" message when we
    # continue the conversation with tool results.
    raw_content: list[dict] = field(default_factory=list)


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("AI_API_KEY")
        self.model = model or os.getenv("AI_MODEL", DEFAULT_MODEL)

        if not self.api_key:
            raise LLMProviderError(
                "AI_API_KEY is not configured. Set the AI_API_KEY environment variable to enable the agent."
            )

        self._client = anthropic.Anthropic(api_key=self.api_key)

    def generate_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict],
        max_tokens: int = 1024,
    ) -> LLMTurnResult:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"LLM provider error: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"LLM request failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        for block in response.content:
            raw_content.append(block.model_dump())
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        return LLMTurnResult(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw_content=raw_content,
        )
