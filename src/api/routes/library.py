"""Deterministic library skills (Google / YouTube / LinkedIn) — no LLM calls."""

from __future__ import annotations

from fastapi import APIRouter

from .models import GoogleSearchBody, LinkedInBody, YouTubeSearchBody


router = APIRouter(prefix="/api/library", tags=["library"])


@router.post("/google")
async def api_google_search(body: GoogleSearchBody) -> dict:
    """Search Google — deterministic, zero LLM calls."""
    from ...skills.library import google_search
    result = await google_search(body.query, max_results=body.max_results)
    return result.to_dict()


@router.post("/youtube")
async def api_youtube_search(body: YouTubeSearchBody) -> dict:
    """Search YouTube — deterministic, zero LLM calls."""
    from ...skills.library import youtube_search
    result = await youtube_search(body.query, max_results=body.max_results)
    return result.to_dict()


@router.post("/linkedin")
async def api_linkedin_profile(body: LinkedInBody) -> dict:
    """Extract a LinkedIn profile — deterministic, zero LLM calls."""
    from ...skills.library import linkedin_extract_profile
    result = await linkedin_extract_profile(body.url)
    return result.to_dict()
