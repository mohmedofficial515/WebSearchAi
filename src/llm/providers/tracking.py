"""TrackingProvider — wraps any LLMClient and records cost after each call."""

from __future__ import annotations

import json

from ..costs import cost_tracker as _tracker


def _tok(text: str) -> int:
    """Rough token estimate: ~4 chars per token, minimum 1."""
    return max(1, len(text) // 4)


class TrackingProvider:
    """Transparent proxy that logs a CostEntry after every LLM call."""

    def __init__(self, inner, provider_name: str) -> None:
        self._inner = inner
        self._name = provider_name

    # ── text ──────────────────────────────────────────────────────────────────

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        prompt = " ".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        )
        result = await self._inner.chat(messages, json_mode=json_mode, **kwargs)
        _tracker.record(
            provider=self._name,
            model=getattr(self._inner, "_text_model", "unknown"),
            input_tokens=_tok(prompt),
            output_tokens=_tok(result),
            endpoint="chat",
        )
        return result

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        result = await self._inner.chat_json(system, user, **kwargs)
        _tracker.record(
            provider=self._name,
            model=getattr(self._inner, "_text_model", "unknown"),
            input_tokens=_tok(system + user),
            output_tokens=_tok(json.dumps(result)),
            endpoint="chat_json",
        )
        return result

    # ── vision ────────────────────────────────────────────────────────────────

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        result = await self._inner.vision(prompt, image_bytes, **kwargs)
        _tracker.record(
            provider=self._name,
            model=getattr(self._inner, "_vision_model", "unknown"),
            input_tokens=_tok(prompt) + 1000,  # flat image-token estimate
            output_tokens=_tok(result),
            endpoint="vision",
        )
        return result

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        result = await self._inner.vision_json(prompt, image_bytes, **kwargs)
        _tracker.record(
            provider=self._name,
            model=getattr(self._inner, "_vision_model", "unknown"),
            input_tokens=_tok(prompt) + 1000,
            output_tokens=_tok(json.dumps(result)),
            endpoint="vision_json",
        )
        return result

    # ── embed ─────────────────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        result = await self._inner.embed(text)
        _tracker.record(
            provider=self._name,
            model=getattr(self._inner, "_embed_model", "embed"),
            input_tokens=_tok(text),
            output_tokens=0,
            endpoint="embed",
        )
        return result

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._inner.close()
