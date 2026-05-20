"""Plugin / skill registry browsing endpoints + static artifact helper."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config import settings


router = APIRouter(tags=["plugins"])


@router.get("/api/plugins")
async def api_list_plugins() -> list[dict]:
    """Return all discovered async skills/plugins."""
    from ...skills.plugin_loader import plugin_loader
    return [s.to_dict() for s in plugin_loader.list()]


@router.get("/api/plugins/{name}")
async def api_get_plugin(name: str) -> dict:
    """Return metadata for a single plugin/skill by name."""
    from ...skills.plugin_loader import plugin_loader
    skill = plugin_loader.get(name)
    if skill is None:
        raise HTTPException(404, f"plugin '{name}' not found")
    return skill.to_dict()


@router.get("/api/artifact/{task_id}/{filename}")
async def get_artifact(task_id: str, filename: str) -> FileResponse:
    p = settings.output_path / "sessions" / task_id / filename
    if not p.exists():
        raise HTTPException(404, "artifact not found")
    return FileResponse(str(p))
