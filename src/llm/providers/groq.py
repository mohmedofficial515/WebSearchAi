"""Groq LLM provider — free-tier ultra-fast inference.

Free tier: 14,400 requests/day · 6,000 tokens/minute
Sign up:   https://console.groq.com
Free models (as of 2026):
  - llama-3.1-8b-instant     → fastest, daily tasks
  - llama-3.3-70b-versatile  → most capable free model
  - mixtral-8x7b-32768       → long context (32K)
  - gemma2-9b-it             → Google Gemma, balanced
  - llama-3.2-11b-vision-preview → vision (free)
"""
from __future__ import annotations
import base64
import json
import re
import httpx

_BASE = "https://api.groq.com/openai/v1"
_DEFAULT_TEXT_MODEL = "llama-3.1-8b-instant"
_VISION_MODEL = "llama-3.2-11b-vision-preview"

FREE_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class GroqProvider:
    """Groq cloud provider — OpenAI-compatible REST API."""

    def __init__(self, api_key: str, text_model: str = _DEFAULT_TEXT_MODEL) -> None:
        self._api_key = api_key
        self._text_model = text_model
        self._vision_model = _VISION_MODEL
        self._embed_model = "unsupported"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_BASE}{path}", json=body, headers=self._headers)
            r.raise_for_status()
            return r.json()

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **_) -> str:
        body: dict = {"model": self._text_model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = await self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, system: str, user: str, **_) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return _safe_json(await self.chat(msgs, json_mode=True))

    async def vision(self, prompt: str, image_bytes: bytes, **_) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        body = {
            "model": self._vision_model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        }
        data = await self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"]

    async def vision_json(self, prompt: str, image_bytes: bytes, **_) -> dict:
        return _safe_json(await self.vision(prompt, image_bytes))

    async def embed(self, text: str, **_) -> list[float]:
        raise NotImplementedError("Groq does not support embeddings — use Gemini or Cohere instead")

    async def close(self) -> None:
        pass
