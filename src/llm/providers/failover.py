"""FailoverProvider — tries providers in order; advances on HTTP 429 or rate-limit errors."""

from __future__ import annotations

import httpx


class FailoverProvider:
    """Wraps a list of LLMClient providers and advances to the next on 429."""

    def __init__(self, providers: list) -> None:
        if not providers:
            raise ValueError("FailoverProvider requires at least one provider")
        self._providers = list(providers)
        self._idx = 0

    @property
    def _current(self):
        return self._providers[self._idx]

    def _try_advance(self) -> bool:
        if self._idx + 1 < len(self._providers):
            self._idx += 1
            return True
        return False

    def _is_rate_limit(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429
        return "rate_limited" in str(exc).lower()

    async def _with_failover(self, method: str, *args, **kwargs):
        while True:
            try:
                return await getattr(self._current, method)(*args, **kwargs)
            except Exception as exc:
                if self._is_rate_limit(exc) and self._try_advance():
                    continue
                raise

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        return await self._with_failover("chat", messages, json_mode=json_mode, **kwargs)

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        return await self._with_failover("chat_json", system, user, **kwargs)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        return await self._with_failover("vision", prompt, image_bytes, **kwargs)

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        return await self._with_failover("vision_json", prompt, image_bytes, **kwargs)

    async def embed(self, text: str) -> list[float]:
        return await self._with_failover("embed", text)

    async def close(self) -> None:
        for p in self._providers:
            await p.close()
