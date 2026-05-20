"""Long-term agent memory: list/forget sites + semantic search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...config import settings


router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/sites")
async def memory_list_sites() -> list[dict]:
    """List all sites stored in long-term agent memory."""
    from ...memory import get_memory
    store = await get_memory()
    return await store.list_sites()


@router.delete("/sites")
async def memory_forget_site(url: str) -> dict:
    """Remove a site and all its data (flows, vectors, logins) from memory."""
    from ...memory import get_memory
    store = await get_memory()
    await store.forget_site(url)
    return {"ok": True, "forgotten": url}


@router.get("/search")
async def memory_search(query: str, k: int = 5) -> list[dict]:
    """Semantic search over agent memory (requires MISTRAL_API_KEY)."""
    if not settings.mistral_api_key:
        raise HTTPException(400, "MISTRAL_API_KEY not configured")
    from ...memory import MemoryRecall, get_memory
    store = await get_memory()
    recall = MemoryRecall(store, settings.mistral_api_key)
    return await recall.search(query, k=k)
