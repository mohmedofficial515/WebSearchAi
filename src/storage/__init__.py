"""Persistent task storage for WebSearchAi.

Usage:
    from src.storage import get_task_store
    store = await get_task_store()
    await store.save_task("task-123", "run", {"goal": "..."}, "queued")
    await store.update_status("task-123", "succeeded", result={"ok": True})
"""
from __future__ import annotations

from .store import TaskStore

_instance: TaskStore | None = None


async def get_task_store(db_path: str = "") -> TaskStore:
    global _instance
    if _instance is None:
        if not db_path:
            from ..config import settings
            db_path = str(settings.output_path / "tasks.db")
        _instance = TaskStore(db_path)
        await _instance.init()
    return _instance


__all__ = ["TaskStore", "get_task_store"]
