"""Google Gemini LLM provider — free tier via Generative Language API.

Free tier: 15 requests/min · 1,500 req/day · 1M tokens/day
Sign up:   https://aistudio.google.com  (create API key in 30 seconds)
Free models (as of 2026):
  - gemini-1.5-flash          → fast, vision + long context (1M tokens)
  - gemini-2.0-flash-exp      → newest, experimental, free
  - gemini-1.5-pro            → most capable (slower, lower free quota)
  - text-embedding-004        → free embeddings (768 dims)
"""
from __future__ import annotations
import base64
import json
import re
import httpx

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_TEXT_MODEL = "gemini-1.5-flash"
_DEFAULT_EMBED_MODEL = "text-embedding-004"

FREE_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
]


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class GeminiProvider:
    """Google Gemini cloud provider — Generative Language REST API."""

    def __init__(self, api_key: str, text_model: str = _DEFAULT_TEXT_MODEL) -> None:
        self._api_key = api_key
        self._text_model = text_model
        self._vision_model = text_model  # same model handles vision
        self._embed_model = _DEFAULT_EMBED_MODEL

    async def _post(self, model: str, action: str, body: dict) -> dict:
        url = f"{_BASE}/{model}:{action}?key={self._api_key}"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _extract_text(data: dict) -> str:
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **_) -> str:
        contents = []
        system_text = None
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            elif m["role"] in ("user", "model"):
                # Gemini uses "model" not "assistant"
                role = "model" if m["role"] == "assistant" else m["role"]
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            else:
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})

        body: dict = {"contents": contents}
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}

        data = await self._post(self._text_model, "generateContent", body)
        return self._extract_text(data)

    async def chat_json(self, system: str, user: str, **_) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return _safe_json(await self.chat(msgs, json_mode=True))

    async def vision(self, prompt: str, image_bytes: bytes, **_) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        body = {"contents": [{"parts": [
            {"text": prompt},
            {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
        ]}]}
        data = await self._post(self._vision_model, "generateContent", body)
        return self._extract_text(data)

    async def vision_json(self, prompt: str, image_bytes: bytes, **_) -> dict:
        return _safe_json(await self.vision(prompt, image_bytes))

    async def embed(self, text: str, **_) -> list[float]:
        body = {"content": {"parts": [{"text": text}]}}
        data = await self._post(self._embed_model, "embedContent", body)
        return data["embedding"]["values"]

    async def close(self) -> None:
        pass
