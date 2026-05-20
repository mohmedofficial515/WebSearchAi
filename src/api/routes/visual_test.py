"""Visual regression skill: capture baselines and diff fresh screenshots."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import VisualBaselineBody, VisualCompareBody


router = APIRouter(prefix="/api/visual-test", tags=["visual-test"])


@router.post("/baseline")
async def api_visual_baseline(body: VisualBaselineBody) -> dict:
    """Capture a visual baseline screenshot for *name*."""
    from ...skills.visual_test import capture_baseline
    path = await capture_baseline(body.url, body.name, headless=body.headless)
    return {"ok": True, "name": body.name, "path": str(path)}


@router.post("/compare")
async def api_visual_compare(body: VisualCompareBody) -> dict:
    """Compare a fresh screenshot against the stored baseline *name*."""
    from ...skills.visual_test import compare
    result = await compare(
        body.url, body.name,
        threshold=body.threshold,
        headless=body.headless,
    )
    return result.to_dict()


@router.get("/baselines")
async def api_visual_list_baselines() -> list[dict]:
    """List all stored visual baselines."""
    from ...skills.visual_test import list_baselines
    return list_baselines()


@router.delete("/baselines/{name}")
async def api_visual_delete_baseline(name: str) -> dict:
    """Delete the baseline *name*."""
    from ...skills.visual_test import delete_baseline
    ok = delete_baseline(name)
    if not ok:
        raise HTTPException(404, f"Baseline '{name}' not found")
    return {"ok": True, "deleted": name}
