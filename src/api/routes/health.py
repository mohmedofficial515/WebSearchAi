"""Root redirect (/ → /chat/) and health probes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse


router = APIRouter(tags=["health"])


@router.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/chat/", status_code=301)


@router.get("/health")
@router.get("/api/health")
async def health() -> dict:
    return {"ok": True, "version": "0.1.0"}
