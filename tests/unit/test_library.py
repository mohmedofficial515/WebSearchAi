"""Unit tests for src/skills/library.py — all browser I/O is mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_session(eval_return=None):
    """Return a BrowserSession mock with all coroutine methods patched."""
    session = MagicMock()
    session.start   = AsyncMock()
    session.stop    = AsyncMock()
    session.goto    = AsyncMock()
    session.type    = AsyncMock()
    session.press   = AsyncMock()
    session.eval_js = AsyncMock(return_value=eval_return)
    page = MagicMock()
    page.url = "https://www.google.com/search?q=test"
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    session.page = page
    return session


_GOOGLE_RESULTS = [
    {"title": "Python docs", "url": "https://docs.python.org", "snippet": "Official docs"},
    {"title": "Real Python",  "url": "https://realpython.com",  "snippet": "Tutorials"},
]

_YT_VIDEOS = [
    {"title": "Async Python", "url": "https://youtube.com/watch?v=abc", "channel": "Tech", "views": "1M", "uploaded": "2 years ago", "duration": "12:34"},
    {"title": "FastAPI Crash Course", "url": "https://youtube.com/watch?v=xyz", "channel": "Dev", "views": "500K", "uploaded": "1 year ago", "duration": "45:00"},
]

_LINKEDIN_DATA = {
    "name": "Jane Doe",
    "headline": "Senior Engineer at Acme",
    "location": "Cairo, Egypt",
    "about": "Passionate about Python.",
    "experience": ["Senior Engineer at Acme", "Engineer at Beta"],
    "education": ["Cairo University"],
    "skills": ["Python", "FastAPI"],
    "connections": "500+",
}


# ── google_search ─────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_google_search_returns_results():
    session = _mock_session(eval_return=_GOOGLE_RESULTS)

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import google_search
        result = await google_search("python async", max_results=5)

    assert result.source == "google"
    assert result.query == "python async"
    assert len(result.results) == 2
    assert result.results[0]["title"] == "Python docs"
    assert result.total == 2


@pytest.mark.unit
async def test_google_search_empty_response():
    session = _mock_session(eval_return=[])

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import google_search
        result = await google_search("xyznotfound")

    assert result.results == []
    assert result.total == 0


@pytest.mark.unit
async def test_google_search_respects_max_results():
    many = _GOOGLE_RESULTS * 10  # 20 items
    session = _mock_session(eval_return=many)

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import google_search
        result = await google_search("test", max_results=3)

    assert len(result.results) <= 3


@pytest.mark.unit
async def test_google_search_always_stops_browser():
    session = _mock_session(eval_return=None)

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import google_search
        await google_search("test")

    session.stop.assert_awaited_once()


# ── youtube_search ────────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_youtube_search_returns_videos():
    session = _mock_session(eval_return=_YT_VIDEOS)

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import youtube_search
        result = await youtube_search("async python")

    assert result.query == "async python"
    assert len(result.videos) == 2
    assert result.videos[0]["channel"] == "Tech"
    assert result.total == 2


@pytest.mark.unit
async def test_youtube_search_always_stops_browser():
    session = _mock_session(eval_return=[])

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import youtube_search
        await youtube_search("test")

    session.stop.assert_awaited_once()


# ── linkedin_extract_profile ──────────────────────────────────────────────────


@pytest.mark.unit
async def test_linkedin_extract_success():
    session = _mock_session(eval_return=_LINKEDIN_DATA)
    session.page.url = "https://www.linkedin.com/in/janedoe"

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import linkedin_extract_profile
        profile = await linkedin_extract_profile("https://www.linkedin.com/in/janedoe")

    assert profile.name == "Jane Doe"
    assert profile.headline == "Senior Engineer at Acme"
    assert "Python" in profile.skills
    assert profile.error is None


@pytest.mark.unit
async def test_linkedin_detects_auth_wall():
    session = _mock_session(eval_return=_LINKEDIN_DATA)
    session.page.url = "https://www.linkedin.com/authwall?trk=..."

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import linkedin_extract_profile
        profile = await linkedin_extract_profile("https://www.linkedin.com/in/janedoe")

    assert profile.error is not None
    assert "login" in profile.error.lower()


@pytest.mark.unit
async def test_linkedin_to_dict_shape():
    session = _mock_session(eval_return=_LINKEDIN_DATA)
    session.page.url = "https://www.linkedin.com/in/janedoe"

    with patch("src.skills.library._new_session", AsyncMock(return_value=session)), \
         patch("src.skills.library._save_to_memory", AsyncMock()):
        from src.skills.library import linkedin_extract_profile
        profile = await linkedin_extract_profile("https://www.linkedin.com/in/janedoe")

    d = profile.to_dict()
    for key in ("url", "name", "headline", "location", "about", "experience", "education", "skills"):
        assert key in d


# ── SearchResult / YouTubeResult to_dict ─────────────────────────────────────


@pytest.mark.unit
def test_search_result_to_dict():
    from src.skills.library import SearchResult
    sr = SearchResult(query="q", results=[{"title": "T", "url": "U", "snippet": "S"}], source="google", total=1)
    d = sr.to_dict()
    assert d["source"] == "google"
    assert d["total"] == 1
    assert d["results"][0]["title"] == "T"


@pytest.mark.unit
def test_youtube_result_to_dict():
    from src.skills.library import YouTubeResult
    yr = YouTubeResult(query="q", videos=[{"title": "V", "url": "U"}], total=1)
    d = yr.to_dict()
    assert d["total"] == 1
    assert d["videos"][0]["title"] == "V"
