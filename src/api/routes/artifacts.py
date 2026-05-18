"""Artifact preview / download / regenerate endpoints.

The Artifact model (src/core/artifacts.py) stores metadata; the actual
file lives under `outputs/artifacts/{task_id}/{content_path}`. These
endpoints serve previews, downloads, and (later) regeneration.

For now we keep an in-memory registry of Artifacts. A persistent store is
out of scope for Phase B; it lands in Phase G alongside the artifacts
ledger UI.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from ...config import settings
from ...core.artifacts import Artifact, artifacts_base


router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


# In-memory registry keyed by artifact_id. Skills register here as they
# produce files; the React UI reads from /api/artifacts/{id}.
_REGISTRY: dict[str, Artifact] = {}


def register_artifact(a: Artifact) -> None:
    _REGISTRY[a.artifact_id] = a


def get_artifact(artifact_id: str) -> Artifact | None:
    return _REGISTRY.get(artifact_id)


def list_for_task(task_id: str) -> list[Artifact]:
    return [a for a in _REGISTRY.values() if a.task_id == task_id]


class RegenerateResponse(BaseModel):
    artifact_id: str
    status: str


def _resolve_file(a: Artifact) -> Path:
    base = artifacts_base(settings.output_path)
    path = a.absolute_path(base)
    if not path.exists():
        raise HTTPException(404, detail="الملف غير موجود")
    return path


@router.get("/{artifact_id}", response_model=Artifact)
async def get_artifact_meta(artifact_id: str) -> Artifact:
    a = _REGISTRY.get(artifact_id)
    if a is None:
        raise HTTPException(404, detail="لا يوجد سجل بهذا المعرف")
    return a


@router.get("/{artifact_id}/preview")
async def preview_artifact(artifact_id: str) -> Response:
    """Inline preview — text-like content is returned as UTF-8; binary
    artifacts return their bytes with the recorded MIME type so the
    browser can render them in an `<iframe>` or `<img>`."""
    a = _REGISTRY.get(artifact_id)
    if a is None:
        raise HTTPException(404, detail="لا يوجد سجل بهذا المعرف")
    path = _resolve_file(a)
    mime = a.mime_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    if mime.startswith("text/") or mime in {"application/json", "image/svg+xml"}:
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type=mime)
    return Response(content=path.read_bytes(), media_type=mime)


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str) -> FileResponse:
    """Force-download with Content-Disposition: attachment. Works for ZIP
    artifacts (site_clone output) the same as any other kind."""
    a = _REGISTRY.get(artifact_id)
    if a is None:
        raise HTTPException(404, detail="لا يوجد سجل بهذا المعرف")
    path = _resolve_file(a)
    return FileResponse(
        path=str(path),
        filename=a.filename,
        media_type=a.mime_type or "application/octet-stream",
    )


@router.post("/{artifact_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_artifact(artifact_id: str) -> RegenerateResponse:
    """Stub — real regeneration is wired per-skill in Phase D/F. We accept
    the call so the UI button isn't a dead end; it's a no-op for now."""
    a = _REGISTRY.get(artifact_id)
    if a is None:
        raise HTTPException(404, detail="لا يوجد سجل بهذا المعرف")
    return RegenerateResponse(artifact_id=artifact_id, status="not_implemented")
