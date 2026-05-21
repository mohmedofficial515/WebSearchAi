"""Task management endpoints (list / get / cancel / events / report / answer).

Distinct from `src/api/tasks.py` which owns the in-memory `TaskManager`
singleton — this module is only the HTTP surface in front of it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...utils.event_bus import bus
from ..tasks import task_manager


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    history: bool = False,
    limit: int = 100,
    kind: str | None = None,
) -> list[dict]:
    """List tasks. Pass ?history=true to include persisted past-session records."""
    if history:
        return await task_manager.list_history(limit=limit, kind=kind)
    return task_manager.list()


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    rec = task_manager.get(task_id)
    if rec:
        return rec.to_dict()
    # Fall back to persistent store for completed tasks from prior sessions
    from ...storage import get_task_store
    store = await get_task_store()
    stored = await store.load_task(task_id)
    if not stored:
        raise HTTPException(404, "task not found")
    return stored


@router.delete("/{task_id}")
async def cancel_task(task_id: str) -> dict:
    ok = task_manager.cancel(task_id)
    if not ok:
        raise HTTPException(409, "cannot cancel task")
    return {"ok": True}


@router.post("/{task_id}/answer")
async def submit_task_answer(task_id: str, body: dict) -> dict:
    """Submit a user answer for a paused design-agent question."""
    from ...core.answer_bus import post_answer
    ok = post_answer(task_id, body)
    if not ok:
        raise HTTPException(404, "no pending question for this task")
    return {"ok": True}


@router.get("/{task_id}/events")
async def get_task_events(task_id: str) -> list[dict]:
    return [e.to_dict() for e in bus.history(task_id)]


@router.get("/{task_id}/report")
async def get_task_report(task_id: str) -> dict:
    """Return the Arabic Markdown report for a task.

    Looks first for the pre-rendered `report.ar.md` written by the
    research flow; if missing (legacy task), regenerates on the fly
    from the stored result JSON.
    """
    from ...config import settings
    from ...reports import render_arabic_report
    from ...storage import get_task_store

    artifacts = settings.output_path / "sessions" / task_id
    report_file = artifacts / "report.ar.md"
    if report_file.exists():
        return {
            "task_id": task_id,
            "markdown": report_file.read_text(encoding="utf-8"),
            "source": "file",
        }

    # Fallback: regenerate from the live task manager or persistent store.
    result_dict: dict | None = None
    rec = task_manager.get(task_id)
    if rec and rec.result and isinstance(rec.result, dict):
        result_dict = rec.result
    if result_dict is None:
        store = await get_task_store()
        stored = await store.load_task(task_id)
        if stored and isinstance(stored.get("result"), dict):
            result_dict = stored["result"]
    if result_dict is None:
        raise HTTPException(404, "no result available for this task")
    return {
        "task_id": task_id,
        "markdown": render_arabic_report(result_dict),
        "source": "generated",
    }
