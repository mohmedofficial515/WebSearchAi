"""Base Protocol that all LLM providers must satisfy.

Tool-calling support is optional and gated by `supports_tools`. The
`Conversation` orchestrator checks that attribute before calling
`chat_with_tools` and falls back to a JSON-gate prompt for providers
that don't expose a native tool API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """A single tool invocation the model emitted."""
    id: str                          # provider-supplied id; we round-trip it on tool_result
    name: str                        # must match a tool in the manifest
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResponse:
    """Unified shape returned by `chat_with_tools`.

    Either `text` is non-empty (plain conversational reply) or
    `tool_calls` is non-empty (the model wants to invoke one or more
    tools). Both can be empty in pathological cases — callers should
    treat that as "model declined to act".
    """
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Provider-native finish reason ("stop", "tool_use", "end_turn", ...).
    # Kept opaque on purpose — callers should read tool_calls/text instead.
    finish_reason: str = ""


@runtime_checkable
class LLMClient(Protocol):
    # Class-level capability flags. Providers that implement
    # `chat_with_tools` set `supports_tools = True`. The default protocol
    # value is False so any provider that hasn't been upgraded yet is
    # routed through the gate-prompt path automatically.
    supports_tools: bool

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str: ...
    async def chat_json(self, system: str, user: str, **kwargs) -> dict: ...
    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str: ...
    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict: ...
    async def embed(self, text: str) -> list[float]: ...
    async def close(self) -> None: ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResponse:
        """Tool-calling chat completion.

        `tools` is a list of JSON-schema tool definitions in
        OpenAI/Anthropic-compatible shape:
            {"name": str, "description": str, "input_schema": {...}}

        Providers that don't natively support tools should set
        `supports_tools = False` and may raise NotImplementedError from
        this method — the orchestrator never calls it in that case.
        """
        ...
