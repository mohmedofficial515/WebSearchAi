"""Mistral provider adapter."""
from __future__ import annotations
import json, re
import httpx
from src.llm.mistral_client import MistralClient as _MistralClient

_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
_EMBED_MODEL = "mistral-embed"


class MistralProvider:
    def __init__(self, api_key: str, text_model: str = "mistral-small-latest", vision_model: str = "pixtral-12b-2409"):
        self._client = _MistralClient(api_key=api_key, text_model=text_model, vision_model=vision_model)
        self._api_key = api_key
        self._text_model = text_model
        self._vision_model = vision_model
        self._embed_model = _EMBED_MODEL

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        return await self._client.chat(messages, json_mode=json_mode)

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        return await self._client.chat_json(system, user, **kwargs)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        return await self._client.vision(prompt, image_bytes)

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        return await self._client.vision_json(prompt, image_bytes)

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _EMBED_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": _EMBED_MODEL, "input": [text]},
            )
            r.raise_for_status()
        return r.json()["data"][0]["embedding"]

    async def close(self) -> None:
        await self._client.close()
