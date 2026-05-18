"""OpenAI provider (GPT-4o, text-embedding-3-small)."""
from __future__ import annotations
import base64, json, re
import httpx

_BASE = "https://api.openai.com/v1"
_TEXT_MODEL = "gpt-4o-mini"
_VISION_MODEL = "gpt-4o"
_EMBED_MODEL = "text-embedding-3-small"


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class OpenAIProvider:
    def __init__(self, api_key: str, text_model: str = _TEXT_MODEL, vision_model: str = _VISION_MODEL):
        self._api_key = api_key
        self._text_model = text_model
        self._vision_model = vision_model
        self._embed_model = _EMBED_MODEL
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_BASE}{path}", headers=self._headers, json=payload)
            r.raise_for_status()
        return r.json()

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        payload: dict = {"model": self._text_model, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._post("/chat/completions", payload)
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = await self.chat(msgs, json_mode=True)
        return _safe_json(text)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}]
        data = await self._post("/chat/completions", {"model": self._vision_model, "messages": msgs})
        return data["choices"][0]["message"]["content"]

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        text = await self.vision(prompt + "\nRespond with valid JSON only.", image_bytes)
        return _safe_json(text)

    async def embed(self, text: str) -> list[float]:
        data = await self._post("/embeddings", {"model": _EMBED_MODEL, "input": text})
        return data["data"][0]["embedding"]

    async def close(self) -> None:
        pass
