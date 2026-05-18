"""Cohere LLM provider — free Trial key, excellent embeddings.

Free tier: 1,000 API calls/month (Trial key, no credit card)
Sign up:   https://cohere.com  → Dashboard → API Keys
Free models (as of 2026):
  - command-r        → best free chat model, multilingual
  - command-r-plus   → most capable (lower free quota)
Embeddings (free):
  - embed-multilingual-v3.0  → 1024 dims, 100+ languages
  - embed-english-v3.0       → 1024 dims, English only (faster)
"""
from __future__ import annotations
import json
import re
import httpx

_BASE = "https://api.cohere.com/v2"
_DEFAULT_TEXT_MODEL = "command-r"
_DEFAULT_EMBED_MODEL = "embed-multilingual-v3.0"

FREE_MODELS = [
    "command-r",
    "command-r-plus",
]


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class CohereProvider:
    """Cohere cloud provider — v2 REST API."""

    def __init__(self, api_key: str, text_model: str = _DEFAULT_TEXT_MODEL) -> None:
        self._api_key = api_key
        self._text_model = text_model
        self._embed_model = _DEFAULT_EMBED_MODEL
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
        cohere_msgs = []
        for m in messages:
            role = m["role"]
            # Cohere v2 accepts: "user", "assistant", "system"
            if role == "assistant":
                cohere_msgs.append({"role": "assistant", "content": m["content"]})
            elif role == "system":
                cohere_msgs.append({"role": "system", "content": m["content"]})
            else:
                cohere_msgs.append({"role": "user", "content": m["content"]})

        body: dict = {"model": self._text_model, "messages": cohere_msgs}
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        data = await self._post("/chat", body)
        return data["message"]["content"][0]["text"]

    async def chat_json(self, system: str, user: str, **_) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return _safe_json(await self.chat(msgs, json_mode=True))

    async def vision(self, prompt: str, image_bytes: bytes, **_) -> str:
        raise NotImplementedError("Cohere does not support vision — use Gemini or Groq instead")

    async def vision_json(self, prompt: str, image_bytes: bytes, **_) -> dict:
        raise NotImplementedError("Cohere does not support vision — use Gemini or Groq instead")

    async def embed(self, text: str, **_) -> list[float]:
        body = {
            "model": self._embed_model,
            "texts": [text],
            "input_type": "search_document",
            "embedding_types": ["float"],
        }
        data = await self._post("/embed", body)
        return data["embeddings"]["float"][0]

    async def close(self) -> None:
        pass
