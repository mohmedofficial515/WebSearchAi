"""Long-term memory for the WebSearchAi agent.

Usage:
    from src.memory import get_memory
    store = await get_memory()
    await store.remember_flow("https://github.com", "search", {"steps": [...]})
    flow = await store.recall_flow("https://github.com", "search")
"""
from __future__ import annotations

from .store import MemoryStore, FlowRecord
from .recall import MemoryRecall

_instance: MemoryStore | None = None


async def get_memory(db_path: str = "") -> MemoryStore:
    global _instance
    if _instance is None:
        if not db_path:
            from ..config import settings
            db_path = str(settings.output_path / "memory.db")
        _instance = MemoryStore(db_path)
        await _instance.init()
    return _instance


__all__ = ["MemoryStore", "MemoryRecall", "FlowRecord", "get_memory"]
