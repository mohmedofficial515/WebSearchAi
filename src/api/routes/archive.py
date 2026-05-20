"""Task archive: smart re-use of past successful runs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import ArchiveCheckBody


router = APIRouter(prefix="/api/archive", tags=["archive"])


@router.get("")
async def archive_list(limit: int = 50, success_only: bool = True) -> list[dict]:
    """Recent archived tasks (newest first)."""
    from ...archive import get_archive
    arc = await get_archive()
    records = await arc.list(limit=limit, success_only=success_only)
    return [r.to_dict() for r in records]


@router.get("/search")
async def archive_search(q: str, limit: int = 10, min_score: float = 0.05) -> dict:
    """Rank archived tasks by TF-IDF similarity to the query.

    Returns: { query, matches: [{task_id, goal, summary, score, matched_terms, ...}] }
    """
    from ...archive import get_archive
    arc = await get_archive()
    matches = await arc.search(q, limit=limit, min_score=min_score)
    return {"query": q, "matches": [m.to_dict() for m in matches]}


@router.post("/check")
async def archive_check(body: ArchiveCheckBody) -> dict:
    """Pre-flight: is there an archived task that already answers this goal?

    Used by the UI to offer "reuse this past result" before spinning up
    the browser.

    Threshold guide:
      0.95+ → effectively identical wording  (auto-suggest reuse)
      0.80  → same intent, different phrasing  (prompt the user)
      0.55  → same topic; surface as "did you mean…"
    """
    from ...archive import get_archive
    arc = await get_archive()
    hit = await arc.find_similar(body.goal, threshold=body.threshold)
    if not hit:
        return {"match": None}
    return {"match": hit.to_dict()}


@router.get("/{task_id}")
async def archive_get(task_id: str) -> dict:
    from ...archive import get_archive
    arc = await get_archive()
    rec = await arc.get(task_id)
    if not rec:
        raise HTTPException(404, f"Archive entry {task_id} not found")
    return rec


@router.delete("/{task_id}")
async def archive_delete(task_id: str) -> dict:
    from ...archive import get_archive
    arc = await get_archive()
    ok = await arc.delete(task_id)
    if not ok:
        raise HTTPException(404, f"Archive entry {task_id} not found")
    return {"ok": True, "deleted": task_id}
