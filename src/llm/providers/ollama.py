"""Ollama local LLM provider (http://localhost:11434)."""
from __future__ import annotations
import json, re
import httpx

_DEFAULT_MODEL = "llama3.2"
_DEFAULT_VISION_MODEL = "llava"
_DEFAULT_EMBED_MODEL = "nomic-embed-text"


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class OllamaProvider:
    supports_tools = False

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        text_model: str = _DEFAULT_MODEL,
        vision_model: str = _DEFAULT_VISION_MODEL,
        embed_model: str = _DEFAULT_EMBED_MODEL,
    ):
        self._base = base_url.rstrip("/")
        self._text_model = text_model
        self._vision_model = vision_model
        self._embed_model = embed_model

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        payload: dict = {"model": self._text_model, "messages": messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self._base}/api/chat", json=payload)
            r.raise_for_status()
        return r.json()["message"]["content"]

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = await self.chat(msgs, json_mode=True)
        return _safe_json(text)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": self._vision_model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self._base}/api/chat", json=payload)
            r.raise_for_status()
        return r.json()["message"]["content"]

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        text = await self.vision(prompt + "\nRespond with valid JSON only.", image_bytes)
        return _safe_json(text)

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self._base}/api/embeddings",
                json={"model": self._embed_model, "prompt": text},
            )
            r.raise_for_status()
        return r.json()["embedding"]

    async def close(self) -> None:
        pass
