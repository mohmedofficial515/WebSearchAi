"""LLM-as-orchestrator for /api/chat.

The Conversation class converts a single user message into one of three
outcomes:

  - **text** — the model wants to reply conversationally (no skill spawn).
  - **tool_call** — the model picked a skill and arguments; the route
    layer dispatches the corresponding task.
  - **need_params** — the chosen skill requires URL/credentials we don't
    have. The frontend renders a parameter prompt.

The decision is made by the LLM, not by hardcoded regex. There are three
paths the orchestrator can take depending on provider capabilities:

  1. **Tool-calling path** (`provider.supports_tools == True`) — native
     function-calling. Best fidelity; supported by Anthropic + OpenAI
     today, expandable to Gemini/Groq/Mistral/OpenRouter later.
  2. **JSON-gate path** (provider exists but no native tools) — a cheap
     LLM call asking for a JSON `{action, skill, ...}` payload. Works
     with any provider that can return JSON.
  3. **Rule-fallback path** (no provider at all) — falls through to the
     legacy `intent_router` so the app keeps working with zero API keys.

This is the architectural fix for the user's complaint that every
message becomes a research task: the model now decides whether to
search or just reply.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from ..llm.providers.base import LLMClient, ToolCall
from ..utils.logger import log
from .intent_router import Intent, detect_intent


ConversationKind = Literal["text", "tool_call", "need_params", "rule_fallback"]


@dataclass
class ConversationResponse:
    """Outcome of `Conversation.handle`."""
    kind: ConversationKind
    # Populated when kind == "text"
    text: str = ""
    # Populated when kind == "tool_call" or "rule_fallback"
    tool: str = ""                              # e.g. "web_search", "clone_page", "login_site"
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    # Populated when kind == "need_params"
    missing_params: list[str] = field(default_factory=list)
    # Diagnostic — which orchestrator path produced this response.
    path: Literal["tool", "gate", "rule"] = "rule"


# ── Tools manifest (single source of truth, used by both LLM paths) ─────────

# Schema follows the unified shape declared in LLMClient.chat_with_tools:
# {name, description, input_schema}. Both Anthropic and OpenAI providers
# translate this into their native shapes internally.
TOOLS_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Run a web research task: search the web, visit candidate pages, "
            "judge their relevance, and synthesize a cited answer in the user's "
            "language. Use this when the user asks ANY question that requires "
            "fresh or external information — current events, comparisons, "
            "tutorials, factual lookups, product research, etc. Do NOT use for "
            "greetings, identity questions, or chit-chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The full research goal in the user's own words.",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "clone_page",
        "description": (
            "Capture a single web page and rebuild it as a clean responsive "
            "Tailwind HTML file. Use when the user asks to clone, copy, "
            "recreate, or mirror a specific URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full http(s) URL of the page."},
                "max_assets": {"type": "integer", "default": 60},
            },
            "required": ["url"],
        },
    },
    {
        "name": "explore_site",
        "description": (
            "Walk a website like a human and produce a structured feature/UX/"
            "tech report. Use when the user asks to analyze, audit, or "
            "explore a specific site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "depth_hint": {"type": "string", "default": "thorough"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "login_site",
        "description": (
            "Log into a website with credentials the user supplied and "
            "optionally persist the session. Use only when the user "
            "explicitly provides email + password."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "email": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["url", "email", "password"],
        },
    },
    {
        "name": "extract_design_tokens",
        "description": (
            "Extract the design tokens (palette, typography, spacing) from a "
            "URL. Use when the user asks for design tokens, colors, or fonts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "find_components",
        "description": (
            "Search for UI component examples online and capture screenshots/HTML. "
            "Use when the user wants to find or collect UI components."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_pages": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]


# ── System prompt for tool-calling + gate paths ─────────────────────────────


def _system_prompt(locale: str) -> str:
    if locale.startswith("ar"):
        return (
            "أنت مساعد ذكي ومحترف. تتحدث العربية والإنجليزية بطلاقة وترد "
            "بنفس لغة المستخدم. لديك مجموعة من الأدوات تستطيع استدعاءها عند "
            "الحاجة فقط:\n\n"
            "- web_search: لأي سؤال يحتاج معلومات من الإنترنت.\n"
            "- clone_page / explore_site / login_site / extract_design_tokens / find_components: "
            "لمهام محددة على روابط بعينها.\n\n"
            "قواعد القرار:\n"
            "1. إذا كان المستخدم يحييك أو يسألك عن نفسك أو يطرح سؤالاً يمكنك "
            "الإجابة عليه من معرفتك العامة — أَجِب نصياً بدون استدعاء أداة.\n"
            "2. إذا كان السؤال يحتاج معلومات حديثة أو خارجية أو مقارنة أو بحث، "
            "استدعِ web_search.\n"
            "3. إذا ذكر المستخدم رابطاً صريحاً وطلب فعلاً محدداً عليه (انسخ، حلّل، "
            "ادخل)، استدعِ الأداة المناسبة.\n"
            "4. لا تخمن مفاتيح أو بيانات اعتماد — اطلبها أولاً من المستخدم.\n"
            "اختصر ردودك النصية ولا تطل."
        )
    return (
        "You are a smart, professional assistant who replies in the user's "
        "language. You have a set of tools you may call ONLY when needed:\n\n"
        "- web_search: for any question requiring fresh or external info.\n"
        "- clone_page / explore_site / login_site / extract_design_tokens / "
        "find_components: for specific actions on specific URLs.\n\n"
        "Decision rules:\n"
        "1. Greetings, identity questions, and anything you can answer from "
        "general knowledge → reply textually, do NOT call a tool.\n"
        "2. Questions needing current/external info or comparisons → call "
        "web_search.\n"
        "3. User mentions a URL and a clear action (clone/analyze/login) → "
        "call the matching tool.\n"
        "4. Never guess credentials — ask the user first.\n"
        "Keep textual replies short."
    )


_GATE_INSTRUCTION_AR = (
    "أنت مساعد ذكي تقرر كيف تتعامل مع رسالة المستخدم. "
    "أعِد JSON صحيحاً فقط بهذا الشكل الدقيق:\n"
    '{"action":"chat"|"web_search"|"clone_page"|"explore_site"|"login_site"|"extract_design_tokens"|"find_components",'
    '"reply":"...الرد الكامل باللغة العربية إذا كان action هو chat وإلا اتركه فارغاً...","reason":"..."}\n\n'
    "قواعد الاختيار:\n"
    "- chat: للتحايا، الأسئلة التعريفية، والمحادثات العامة التي تعرف إجابتها. عند اختيار chat اكتب الرد الكامل في حقل reply.\n"
    "- web_search: لأي سؤال يحتاج معلومات حديثة أو خارجية.\n"
    "- الأدوات الأخرى: عندما يذكر المستخدم رابطاً وفعلاً محدداً عليه.\n"
    "لا تكتب أي شيء خارج JSON."
)

_GATE_INSTRUCTION_EN = (
    "You are a smart assistant deciding how to handle a user message. "
    "Return ONLY valid JSON in this exact shape:\n"
    '{"action":"chat"|"web_search"|"clone_page"|"explore_site"|"login_site"|"extract_design_tokens"|"find_components",'
    '"reply":"...full reply text if action is chat, else empty string...","reason":"..."}\n\n'
    "Rules:\n"
    "- chat: greetings, identity questions, general knowledge you can answer directly. When chat, write the full reply in the reply field.\n"
    "- web_search: anything requiring current or external information.\n"
    "- other tools: when user names a specific URL and action.\n"
    "Return nothing outside the JSON object."
)


# Maps the LLM gate's `action` string and detected intent kinds onto the
# tool names exposed by the manifest. The intent_router uses "research"
# for the default research case; the tool manifest calls it "web_search".
_INTENT_TO_TOOL: dict[str, str] = {
    "research": "web_search",
    "clone": "clone_page",
    "explore": "explore_site",
    "login": "login_site",
    "design_tokens": "extract_design_tokens",
    "components": "find_components",
    # signup / temp_signup intentionally not surfaced as tools yet —
    # they require interactive credential capture.
}


def _intent_to_tool_name(kind: str) -> str | None:
    return _INTENT_TO_TOOL.get(kind)


def _missing_params_for(tool: str, args: dict[str, Any]) -> list[str]:
    """Return the list of required-but-missing parameters for a tool call."""
    spec = next((t for t in TOOLS_MANIFEST if t["name"] == tool), None)
    if not spec:
        return []
    required = spec.get("input_schema", {}).get("required") or []
    return [p for p in required if not args.get(p)]


# ── Orchestrator ────────────────────────────────────────────────────────────


class Conversation:
    """Stateless orchestrator — one instance per request is fine.

    The caller (`/api/chat`) constructs a Conversation, calls `handle`,
    and then converts the returned `ConversationResponse` into a
    `ChatResponse` (mode=chat / mode=single / mode=need_params).
    """

    def __init__(
        self,
        provider: LLMClient | None,
        *,
        locale: str = "ar",
        history: list[dict[str, str]] | None = None,
        tool_timeout: float = 20.0,
    ) -> None:
        self._provider = provider
        self._locale = locale
        self._history = history or []
        self._tool_timeout = tool_timeout

    # ── Public API ──────────────────────────────────────────────────────────

    async def handle(self, message: str) -> ConversationResponse:
        # Path selection — see module docstring for the three paths.
        if self._provider is not None and getattr(self._provider, "supports_tools", False):
            try:
                return await self._tool_call_path(message)
            except (asyncio.TimeoutError, OSError, ValueError, RuntimeError) as exc:
                log.exception("Tool-call path failed; falling back to gate")
                # Fall through to gate path — same provider, narrower call.
                _ = exc
        if self._provider is not None:
            try:
                return await self._gate_path(message)
            except (asyncio.TimeoutError, OSError, ValueError, RuntimeError) as exc:
                log.exception("LLM gate path failed; falling back to rule router")
                _ = exc
        return self._rule_fallback_path(message)

    # ── Tool-calling path ───────────────────────────────────────────────────

    async def _tool_call_path(self, message: str) -> ConversationResponse:
        assert self._provider is not None
        messages = [
            {"role": "system", "content": _system_prompt(self._locale)},
            *self._history,
            {"role": "user", "content": message},
        ]
        response = await asyncio.wait_for(
            self._provider.chat_with_tools(messages, TOOLS_MANIFEST, max_tokens=1024),
            timeout=self._tool_timeout,
        )
        if response.tool_calls:
            # First tool wins. Multi-tool calls (rare in our manifest) would
            # need a pipeline-style execution which already exists in
            # Orchestrator — defer that for a later milestone.
            call = response.tool_calls[0]
            return self._wrap_tool_call(call.name, call.arguments, path="tool")
        # No tool call → conversational reply.
        return ConversationResponse(
            kind="text",
            text=response.text or self._fallback_text(),
            path="tool",
        )

    # ── LLM-gate path ───────────────────────────────────────────────────────

    async def _gate_path(self, message: str) -> ConversationResponse:
        """Cheap JSON-only LLM call for providers that don't expose native tools."""
        assert self._provider is not None
        system = _GATE_INSTRUCTION_AR if self._locale.startswith("ar") else _GATE_INSTRUCTION_EN

        user_prompt = ""
        if self._history:
            user_prompt += "Recent conversation history for context:\n"
            for msg in self._history:
                role = "User" if msg.get("role") == "user" else "Assistant"
                user_prompt += f"{role}: {msg.get('content')}\n"
            user_prompt += "\n"
        user_prompt += f"Current message: {message}"

        data = await asyncio.wait_for(
            self._provider.chat_json(system, user_prompt),
            timeout=self._tool_timeout,
        )

        action = str((data or {}).get("action") or "chat").strip()

        if action == "chat" or action not in {t["name"] for t in TOOLS_MANIFEST}:
            # Gate decided to chat. Use the reply baked into the gate JSON
            # (avoids a second LLM call and prevents session contamination on
            # web-session providers like DeepSeek/ChatGPT that share a browser
            # session across calls — a second call would see the JSON context
            # and echo JSON back).
            reply = str((data or {}).get("reply") or "").strip()
            if not reply:
                # Fallback: gate didn't include a reply (older format) — make
                # a separate text call. This is safe for API providers that
                # don't share session state.
                reply = await self._textual_reply(message)
            if not reply:
                reply = self._fallback_text()
            return ConversationResponse(kind="text", text=reply, path="gate")

        # Gate picked a tool. The gate prompt is intentionally minimal — it
        # does NOT extract arguments. For tools that need a URL we fall back
        # to the legacy rule extractor, which already pulls URLs and
        # credentials out of natural-language Arabic/English.
        intent = detect_intent(message)
        return self._wrap_intent_as_tool(action, intent, path="gate")

    async def _textual_reply(self, message: str) -> str:
        """Generate a plain chat reply (used by gate and as a last resort)."""
        assert self._provider is not None
        try:
            reply = await asyncio.wait_for(
                self._provider.chat([
                    {"role": "system", "content": _system_prompt(self._locale)},
                    *self._history,
                    {"role": "user", "content": message},
                ]),
                timeout=self._tool_timeout,
            )
            return reply.strip() or self._fallback_text()
        except (asyncio.TimeoutError, OSError, ValueError, RuntimeError):
            return self._fallback_text()

    # ── Rule fallback ───────────────────────────────────────────────────────

    def _rule_fallback_path(self, message: str) -> ConversationResponse:
        intent = detect_intent(message)
        if intent.kind == "chat":
            return ConversationResponse(
                kind="text",
                text=self._fallback_text(),
                path="rule",
            )
        tool = _intent_to_tool_name(intent.kind)
        if not tool:
            # Unrecognized intent — surface as chat with a placeholder.
            return ConversationResponse(kind="text", text=self._fallback_text(), path="rule")
        return self._wrap_intent_as_tool(tool, intent, path="rule")

    # ── Helpers shared by paths ─────────────────────────────────────────────

    def _wrap_tool_call(
        self, tool: str, args: dict[str, Any], *, path: Literal["tool", "gate", "rule"]
    ) -> ConversationResponse:
        missing = _missing_params_for(tool, args)
        if missing:
            return ConversationResponse(
                kind="need_params",
                tool=tool,
                tool_arguments=args,
                missing_params=missing,
                path=path,
            )
        return ConversationResponse(
            kind="tool_call",
            tool=tool,
            tool_arguments=args,
            path=path,
        )

    def _wrap_intent_as_tool(
        self, tool: str, intent: Intent, *, path: Literal["tool", "gate", "rule"]
    ) -> ConversationResponse:
        """Translate the legacy Intent shape into a unified tool_call response.

        Used by gate + rule paths where the LLM/router gives us a tool
        name but not structured arguments — we lift the URL/params off
        the Intent (which already extracts them).
        """
        args: dict[str, Any] = {}
        if intent.url:
            if tool == "web_search":
                args["goal"] = intent.goal or ""
            elif tool == "find_components":
                args["query"] = (intent.params.get("query") or intent.goal or "").strip()
            else:
                args["url"] = intent.url
        elif tool == "web_search":
            args["goal"] = intent.goal or ""
        elif tool == "find_components":
            args["query"] = (intent.params.get("query") or intent.goal or "").strip()
        # Pull through credential / depth / max_pages params unchanged.
        for key in ("email", "password", "depth_hint", "max_pages", "max_assets"):
            if key in intent.params and intent.params[key]:
                args[key] = intent.params[key]

        return self._wrap_tool_call(tool, args, path=path)

    def _fallback_text(self) -> str:
        if self._locale.startswith("ar"):
            return "أهلاً وسهلاً! كيف يمكنني مساعدتك اليوم؟"
        return "Hello! How can I help you today?"


# Convenience JSON dump for debugging — surfaces the manifest the
# orchestrator will hand to the LLM. Useful in tests + ad-hoc CLI.
def manifest_json() -> str:
    return json.dumps(TOOLS_MANIFEST, ensure_ascii=False, indent=2)


__all__ = [
    "Conversation",
    "ConversationResponse",
    "ConversationKind",
    "TOOLS_MANIFEST",
    "manifest_json",
]
