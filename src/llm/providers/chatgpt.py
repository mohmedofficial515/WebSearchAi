"""ChatGPT provider — talks to chatgpt.com via a Node subprocess that wraps
the `ai-providers-direct` package's chatgpt namespace (Playwright + persistent
Chrome profile, no API key required).

Why a subprocess (same reason as DeepSeek):
  - The TS package's transport boots a Playwright Chrome to defeat the
    Cloudflare + sentinel anti-bot stack chatgpt.com sits behind. Calling
    that from Python directly would mean porting the whole Playwright glue
    + JSON-Patch SSE parser. The bridge is the simplest seam.

Auth model differs from DeepSeek:
  - No token. The user runs `npm run chatgpt:setup` once inside the
    `ai-providers-direct` install, which opens a Chrome window for sign-in
    and persists the cookies in `.chatgpt-research/chrome-profile/`.
  - This provider is "configured" iff that profile dir exists.

Capabilities:
  - text chat: yes, with auto-continuation on truncation
  - tools / function-calling: no (chatgpt.com doesn't expose it)
  - vision: not yet wired through the bridge
  - embeddings: not exposed by chatgpt.com — use a different provider
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from .base import ToolCallResponse


def _bridge_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "chatgpt_bridge.mjs"


def _profile_dir() -> Path:
    """The persistent Chrome profile lives next to the ai-providers-direct
    install (the bridge pins AI_PROVIDERS_CONSUMER_ROOT there). Used by the
    catalog endpoint to set `is_configured`."""
    return (
        Path(__file__).resolve().parents[4]
        / "ai-providers-direct"
        / ".chatgpt-research"
        / "chrome-profile"
    )


def is_setup_complete() -> bool:
    """True iff `npm run chatgpt:setup` has been completed at least once."""
    return _profile_dir().exists()


def _format_messages(messages: list[dict]) -> str:
    """Flatten OpenAI-style messages into a single prompt. chatgpt.com is
    single-prompt-per-turn (the session preserves history server-side), so
    we collapse the assistant/system context the same way the DeepSeek
    provider does for symmetry."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if role == "system":
            parts.append(f"[SYSTEM]\n{content}")
        elif role == "assistant":
            parts.append(f"[ASSISTANT]\n{content}")
        else:
            parts.append(content if role == "user" else f"[{role.upper()}]\n{content}")
    return "\n\n".join(p for p in parts if p)


class ChatGPTProvider:
    supports_tools = False

    def __init__(
        self,
        model: str = "auto",
        *,
        node_path: str = "node",
        timeout_ms: int = 180_000,
    ) -> None:
        self._text_model = model
        self._node_path = node_path
        self._timeout_ms = timeout_ms
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def _ensure_proc(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        bridge = _bridge_path()
        if not bridge.exists():
            raise RuntimeError(f"ChatGPT bridge not found: {bridge}")
        self._proc = await asyncio.create_subprocess_exec(
            self._node_path,
            str(bridge),
            cwd=str(bridge.parent.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        return self._proc

    async def _send(self, req: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            proc = await self._ensure_proc()
            assert proc.stdin is not None and proc.stdout is not None
            line = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
            proc.stdin.write(line)
            await proc.stdin.drain()

            chunks: list[str] = []
            session_id: str | None = None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    err_bytes = await proc.stderr.read() if proc.stderr else b""
                    self._proc = None
                    raise RuntimeError(
                        f"ChatGPT bridge exited unexpectedly: "
                        f"{err_bytes.decode('utf-8', 'replace')[:500]}"
                    )
                try:
                    evt = json.loads(raw.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                kind = evt.get("event")
                if kind == "chunk":
                    chunks.append(evt.get("text", ""))
                elif kind == "session":
                    session_id = evt.get("session_id")
                elif kind == "done":
                    return {
                        "text": evt.get("text") or "".join(chunks),
                        "session_id": session_id,
                        "conversation_id": evt.get("conversation_id"),
                        "message_id": evt.get("message_id"),
                        "finish_reason": evt.get("finish_reason"),
                    }
                elif kind == "error":
                    raise RuntimeError(
                        f"ChatGPT bridge: {evt.get('type')}: {evt.get('message')}"
                    )

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        prompt = _format_messages(messages)
        if json_mode:
            prompt += "\n\nRespond with a single valid JSON object only, no other text."
        out = await self._send({
            "op": "chat",
            "prompt": prompt,
            "model": self._text_model,
            "timeout_ms": self._timeout_ms,
        })
        return out["text"] or ""

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = await self.chat(msgs, json_mode=True)
        return _safe_json(text)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        raise NotImplementedError(
            "ChatGPT vision (file upload) is not wired through the bridge yet — "
            "use another provider (Mistral / OpenAI API / Anthropic) for vision."
        )

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        raise NotImplementedError("ChatGPT vision not available via this bridge.")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "chatgpt.com doesn't expose embeddings. Configure Mistral/OpenAI/Cohere instead."
        )

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResponse:
        raise NotImplementedError(
            "ChatGPT web provider does not expose native tool-calling; "
            "the orchestrator should route through the gate-prompt path."
        )


def _safe_json(text: str) -> dict:
    import re
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}
