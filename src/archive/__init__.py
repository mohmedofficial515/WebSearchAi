"""Smart task archive — durable memory of completed goals.

Saves every successful task (goal + summary + full result) and provides
TF-IDF-based semantic-ish retrieval so that re-asking the same (or a
very similar) question returns the cached answer instantly instead of
re-running the browser. Works for Arabic + English + mixed-language
goals, with no external API dependency.

Quick start:
    from src.archive import get_archive
    arc = await get_archive()
    await arc.save(task_id, goal, result_dict)
    hit = await arc.find_similar(goal, threshold=0.55)
    matches = await arc.search("real estate Saudi", limit=10)
"""
from __future__ import annotations

from .store import ArchiveStore, ArchiveRecord, Match

_instance: ArchiveStore | None = None


async def get_archive(db_path: str = "") -> ArchiveStore:
    global _instance
    if _instance is None:
        if not db_path:
            from ..config import settings
            db_path = str(settings.output_path / "archive.db")
        _instance = ArchiveStore(db_path)
        await _instance.init()
    return _instance


__all__ = ["ArchiveStore", "ArchiveRecord", "Match", "get_archive"]
