"""Conversation orchestrator — three-path coverage.

Path A: tool-call (provider.supports_tools = True)
Path B: LLM-gate    (provider.supports_tools = False, provider exists)
Path C: rule        (provider = None)
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.conversation import (
    Conversation,
    TOOLS_MANIFEST,
    manifest_json,
)
from src.llm.providers.base import ToolCall, ToolCallResponse


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakeToolProvider:
    """Provider that announces tool support and returns a scripted response."""

    supports_tools = True

    def __init__(self, response: ToolCallResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 1024,
        **_: Any,
    ) -> ToolCallResponse:
        self.calls.append({"messages": messages, "tools": tools, "max_tokens": max_tokens})
        return self._response

    async def chat(self, messages: list[dict], **_: Any) -> str:
        return "fallback text"

    async def chat_json(self, system: str, user: str, **_: Any) -> dict:
        return {"action": "chat", "reason": "fallback"}


class _FakeGateProvider:
    """Provider without native tools — exercises the gate path."""

    supports_tools = False

    def __init__(self, gate_action: str, chat_reply: str = "نص محادثة") -> None:
        self._gate_action = gate_action
        self._chat_reply = chat_reply
        self.gate_calls = 0
        self.chat_calls = 0

    async def chat_json(self, system: str, user: str, **_: Any) -> dict:
        self.gate_calls += 1
        return {"action": self._gate_action, "reason": "test"}

    async def chat(self, messages: list[dict], **_: Any) -> str:
        self.chat_calls += 1
        return self._chat_reply


# ── Tool-call path ──────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_tool_call_path_returns_tool_call() -> None:
    provider = _FakeToolProvider(ToolCallResponse(
        tool_calls=[ToolCall(id="t1", name="web_search", arguments={"goal": "find python news"})],
        finish_reason="tool_use",
    ))
    conv = Conversation(provider, locale="en")  # type: ignore[arg-type]
    result = await conv.handle("what's new in python?")
    assert result.kind == "tool_call"
    assert result.tool == "web_search"
    assert result.tool_arguments["goal"] == "find python news"
    assert result.path == "tool"


@pytest.mark.unit
async def test_tool_call_path_returns_text_when_no_tools() -> None:
    """When the LLM replies without calling any tool, we serve it as
    a conversational reply — no skill spawn."""
    provider = _FakeToolProvider(ToolCallResponse(text="مرحباً! كيف يمكنني مساعدتك؟"))
    conv = Conversation(provider, locale="ar")  # type: ignore[arg-type]
    result = await conv.handle("مرحبا")
    assert result.kind == "text"
    assert "مرحب" in result.text
    assert result.path == "tool"


@pytest.mark.unit
async def test_tool_call_missing_required_param_surfaces_need_params() -> None:
    """If the LLM picks clone_page but forgets the url, the orchestrator
    surfaces need_params so the UI can prompt the user."""
    provider = _FakeToolProvider(ToolCallResponse(
        tool_calls=[ToolCall(id="t1", name="clone_page", arguments={})],
    ))
    conv = Conversation(provider, locale="en")  # type: ignore[arg-type]
    result = await conv.handle("clone the page")
    assert result.kind == "need_params"
    assert "url" in result.missing_params


# ── Gate path ───────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_gate_path_chat_action_returns_text() -> None:
    provider = _FakeGateProvider(gate_action="chat", chat_reply="أهلاً!")
    conv = Conversation(provider, locale="ar")  # type: ignore[arg-type]
    result = await conv.handle("مرحبا")
    assert result.kind == "text"
    assert result.text == "أهلاً!"
    assert result.path == "gate"
    assert provider.gate_calls == 1
    assert provider.chat_calls == 1


@pytest.mark.unit
async def test_gate_path_search_action_returns_tool_call() -> None:
    """Gate picks web_search; orchestrator lifts goal off the message."""
    provider = _FakeGateProvider(gate_action="web_search")
    conv = Conversation(provider, locale="en")  # type: ignore[arg-type]
    result = await conv.handle("best python web frameworks 2026")
    assert result.kind == "tool_call"
    assert result.tool == "web_search"
    assert "python" in result.tool_arguments.get("goal", "")
    assert result.path == "gate"


@pytest.mark.unit
async def test_gate_path_clone_with_url_in_message() -> None:
    """When gate picks clone_page and the message contains a URL, the
    legacy intent_router extracts it for the tool_arguments."""
    provider = _FakeGateProvider(gate_action="clone_page")
    conv = Conversation(provider, locale="ar")  # type: ignore[arg-type]
    result = await conv.handle("انسخ هذه الصفحة https://example.com/page")
    assert result.kind == "tool_call"
    assert result.tool == "clone_page"
    assert result.tool_arguments.get("url") == "https://example.com/page"


# ── Rule fallback path ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_rule_fallback_greeting() -> None:
    """No provider at all → rule path; greetings get the canned reply."""
    conv = Conversation(None, locale="ar")
    result = await conv.handle("مرحبا")
    assert result.kind == "text"
    assert result.path == "rule"


@pytest.mark.unit
async def test_rule_fallback_research() -> None:
    """No provider at all → rule path; non-greetings become web_search."""
    conv = Conversation(None, locale="en")
    result = await conv.handle("what is the meaning of recursion?")
    assert result.kind == "tool_call"
    assert result.tool == "web_search"
    assert result.path == "rule"


# ── Manifest sanity ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_manifest_has_required_tools() -> None:
    """The six tools the plan promised must all be in the manifest."""
    names = {t["name"] for t in TOOLS_MANIFEST}
    assert {"web_search", "clone_page", "explore_site", "login_site",
            "extract_design_tokens", "find_components"} <= names


@pytest.mark.unit
def test_manifest_json_round_trips() -> None:
    """manifest_json() must be valid JSON and decode back to the same set."""
    import json
    data = json.loads(manifest_json())
    assert isinstance(data, list)
    assert {t["name"] for t in data} == {t["name"] for t in TOOLS_MANIFEST}
