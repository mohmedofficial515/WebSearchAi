"""Mistral chat + vision client with JSON-mode helpers and retry."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import settings
from ..utils.logger import log

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


class MistralError(RuntimeError):
    pass


class MistralAuthError(RuntimeError):
    """Raised when authentication fails (401 or 403) to prevent endless retries."""
    pass


class MistralClient:
    def __init__(
        self,
        api_key: str | None = None,
        text_model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.mistral_api_key
        if not self.api_key:
            raise MistralAuthError(
                "MISTRAL_API_KEY missing. Set it in .env (get a free key at "
                "https://console.mistral.ai/)"
            )
        self.text_model = text_model or settings.mistral_text_model
        self.vision_model = vision_model or settings.mistral_vision_model
        self._client = httpx.AsyncClient(timeout=90.0)

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, MistralError)),
        retry_error_callback=lambda state: None, # Let the original exception propagate directly instead of wrapped in RetryError
    )
    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        r = await self._client.post(MISTRAL_API_URL, headers=headers, json=payload)
        if r.status_code == 429:
            log.warning("⏳ Mistral rate-limited; backing off…")
            raise MistralError("rate_limited")
        if r.status_code in (401, 403):
            # Auth error - raising a specific error class will not be retried if we exclude it, or we can raise it and bypass retry entirely.
            # But retry_if_exception_type covers MistralError, and MistralAuthError inherits from MistralError.
            # Let's make sure it raises and we don't retry by either:
            # A) Not inheriting MistralAuthError from MistralError, or
            # B) Handling it explicitly or raising a custom non-retried exception class.
            # Since retry_if_exception_type checks isinstance(), if MistralAuthError inherits from MistralError, it WILL be retried.
            # Therefore, we should either:
            # 1. NOT inherit MistralAuthError from MistralError (e.g. let it inherit directly from RuntimeError), or
            # 2. Add custom logic or check in retry predicate.
            # Let's inherit from Exception/RuntimeError directly and handle it so that it is NOT retried!
            raise MistralAuthError(f"Authentication failed ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 500:
            raise MistralError(f"server_error {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise MistralError(f"client_error {r.status_code}: {r.text[:300]}")
        return r.json()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.text_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._request(payload)
        return data["choices"][0]["message"]["content"]

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        text = await self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return _safe_json(text)

    async def vision(
        self,
        prompt: str,
        image_path: str | Path | None = None,
        image_bytes: bytes | None = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        if image_bytes is None:
            if image_path is None:
                raise ValueError("Provide image_path or image_bytes")
            image_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:image/png;base64,{b64}"
        payload: dict[str, Any] = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": data_url},
                    ],
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._request(payload)
        return data["choices"][0]["message"]["content"]

    async def vision_json(
        self,
        prompt: str,
        image_bytes: bytes,
        **kw,
    ) -> dict[str, Any]:
        text = await self.vision(
            prompt=prompt, image_bytes=image_bytes, json_mode=True, **kw
        )
        return _safe_json(text)


def _safe_json(text: str) -> dict[str, Any]:
    """Parse JSON, fall back to extracting a JSON block from the text."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise MistralError(f"Bad JSON from Mistral: {e}\n---\n{text[:500]}")
        raise MistralError(f"No JSON in Mistral response:\n{text[:500]}")
