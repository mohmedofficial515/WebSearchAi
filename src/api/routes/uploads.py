"""POST /api/uploads — accept multipart file uploads from the composer.

Files are stored under `outputs/uploads/{uuid}/` and exposed via the
existing `/artifacts` static mount. The composer hands the returned URL
back to the chat message as an `attachments[]` entry.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ...config import settings


router = APIRouter(prefix="/api", tags=["uploads"])


# Reasonable cap so a stray 5GB drag-and-drop doesn't fill the disk.
MAX_BYTES = 25 * 1024 * 1024  # 25 MB


class UploadResponse(BaseModel):
    attachment_id: str
    url: str
    mime: str
    size: int


@router.post("/uploads", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    attachment_id = uuid.uuid4().hex
    target_dir = settings.output_path / "uploads" / attachment_id
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")[:120]
    target = target_dir / safe_name

    # Stream to disk in 1MB chunks so big files don't blow up RAM.
    written = 0
    with target.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(413, detail="حجم الملف يتجاوز الحد الأقصى (25 ميجابايت)")
            f.write(chunk)

    # /artifacts is mounted on the output_path root in main.py, so the
    # URL path is relative to that mount.
    url = f"/artifacts/uploads/{attachment_id}/{safe_name}"
    return UploadResponse(
        attachment_id=attachment_id,
        url=url,
        mime=file.content_type or "application/octet-stream",
        size=written,
    )
