"""Embedding-based semantic memory recall using Mistral embed API."""
from __future__ import annotations
import math
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .store import MemoryStore

_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
_EMBED_MODEL = "mistral-embed"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-10)


class MemoryRecall:
    def __init__(self, store: MemoryStore, api_key: str):
        self._store = store
        self._api_key = api_key

    async def _embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _EMBED_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": _EMBED_MODEL, "input": [text]},
            )
            r.raise_for_status()
        return r.json()["data"][0]["embedding"]

    async def remember(self, site: str, text: str, metadata: dict | None = None) -> None:
        embedding = await self._embed(text)
        await self._store.save_vector(site, text, embedding, metadata)

    async def search(self, query: str, k: int = 5) -> list[dict]:
        q_emb = await self._embed(query)
        all_vecs = await self._store.get_all_vectors()
        scored = [
            {**v, "score": _cosine(q_emb, v["embedding"])}
            for v in all_vecs
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]
