"""DeepSeek provider — talks to chat.deepseek.com via a Node subprocess
that wraps the `ai-providers-direct` package (Bearer + PoW WASM + SSE).

We can't talk to DeepSeek's web protocol directly from Python: the PoW
challenge uses a WASM module DeepSeek itself ships, and re-implementing
the JSON-Patch SSE stream parser would be a maintenance burden. Instead
we spawn `scripts/deepseek_bridge.mjs` (Node) and exchange JSON-lines
over stdio. The bridge owns the session/message-id chain across turns
inside one process.

Vision / embeddings: DeepSeek's web protocol doesn't expose embeddings,
and the file-upload path for vision is not wired through here yet.
Both methods raise NotImplementedError so the caller can fall back to
another provider when needed.

Tools: DeepSeek's web chat doesn't expose a JSON tool-call interface,
so `supports_tools = False`. The orchestrator routes us through the
gate-prompt path.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .base import ToolCallResponse


def _bridge_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "deepseek_bridge.mjs"


def _format_messages(messages: list[dict]) -> str:
    """Flatten an OpenAI-style message list into a single prompt for the
    DeepSeek web protocol (which is single-turn-per-call + a session)."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        if role == "system":
            parts.append(f"[SYSTEM]\n{content}")
        elif role == "assistant":
            parts.append(f"[ASSISTANT]\n{content}")
        else:
            parts.append(content if role == "user" else f"[{role.upper()}]\n{content}")
    return "\n\n".join(p for p in parts if p)


class DeepSeekProvider:
    supports_tools = False

    def __init__(
        self,
        token: str = "",
        *,
        thinking: bool = False,
        node_path: str = "node",
        timeout_ms: int = 180_000,
    ) -> None:
        self._token = token or os.environ.get("DEEPSEEK_USER_TOKEN", "")
        self._thinking = thinking
        self._node_path = node_path
        self._timeout_ms = timeout_ms
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def _ensure_proc(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        bridge = _bridge_path()
        if not bridge.exists():
            raise RuntimeError(f"DeepSeek bridge not found: {bridge}")
        env = os.environ.copy()
        if self._token:
            env["DEEPSEEK_USER_TOKEN"] = self._token
        self._proc = await asyncio.create_subprocess_exec(
            self._node_path,
            str(bridge),
            cwd=str(bridge.parent.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        return self._proc

    async def _send(self, req: dict[str, Any]) -> dict[str, Any]:
        """Send one request, drain stream events, return the terminal frame."""
        async with self._lock:
            proc = await self._ensure_proc()
            assert proc.stdin is not None and proc.stdout is not None
            line = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
            proc.stdin.write(line)
            await proc.stdin.drain()

            chunks: list[str] = []
            reasoning: list[str] = []
            session_id: str | None = None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    # Bridge died. Surface stderr so the user can diagnose.
                    err_bytes = await proc.stderr.read() if proc.stderr else b""
                    self._proc = None
                    raise RuntimeError(
                        f"DeepSeek bridge exited unexpectedly: "
                        f"{err_bytes.decode('utf-8', 'replace')[:500]}"
                    )
                try:
                    evt = json.loads(raw.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                kind = evt.get("event")
                if kind == "chunk":
                    chunks.append(evt.get("text", ""))
                elif kind == "reasoning":
                    reasoning.append(evt.get("text", ""))
                elif kind == "session":
                    session_id = evt.get("session_id")
                elif kind == "done":
                    return {
                        "text": evt.get("text") or "".join(chunks),
                        "reasoning": evt.get("reasoning") or "".join(reasoning),
                        "session_id": evt.get("session_id") or session_id,
                        "message_id": evt.get("message_id"),
                        "finish_reason": evt.get("finish_reason"),
                    }
                elif kind == "error":
                    raise RuntimeError(
                        f"DeepSeek bridge: {evt.get('type')}: {evt.get('message')}"
                    )

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        prompt = _format_messages(messages)
        if json_mode:
            prompt += "\n\nأجب بكائن JSON صالح فقط، بدون أي نص خارج JSON."
        out = await self._send({
            "op": "chat",
            "prompt": prompt,
            "thinking": self._thinking,
            "timeout_ms": self._timeout_ms,
        })
        return out["text"] or ""

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = await self.chat(msgs, json_mode=True)
        return _safe_json(text)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        raise NotImplementedError(
            "DeepSeek vision (file-upload path) is not wired through the bridge yet — "
            "configure another provider (Mistral / OpenAI / Anthropic) for vision."
        )

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        raise NotImplementedError("DeepSeek vision not available via this bridge.")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "DeepSeek's web protocol doesn't expose embeddings. "
            "Configure Mistral/OpenAI/Cohere for embeddings."
        )

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
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
            "DeepSeek web provider does not expose native tool-calling; "
            "the orchestrator should route through the gate-prompt path."
        )


def _safe_json(text: str) -> dict:
    import re
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}
