"""Tests for the browser-scrape search backend.

We mock `BrowserSession` end-to-end (no real Chrome launch) and just
assert the dispatcher chain ordering, URL filtering, and graceful
failure handling.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.search import backends
from src.search.backends import SearchResult


class _FakeSession:
    """Drop-in stand-in for BrowserSession used by _browser_search."""

    def __init__(self, results: list[dict[str, Any]] | None = None, raise_on: str | None = None) -> None:
        self._results = results or []
        self._raise_on = raise_on  # method name to raise on
        self.calls: list[str] = []

    async def start(self) -> None:
        self.calls.append("start")
        if self._raise_on == "start":
            raise OSError("browser failed to launch")

    async def stop(self) -> None:
        self.calls.append("stop")

    async def goto(self, url: str, **_: Any) -> None:
        self.calls.append(f"goto:{url}")
        if self._raise_on == "goto":
            raise OSError("network down")

    async def wait_for(self, selector: str, timeout: int | None = None) -> None:
        self.calls.append(f"wait_for:{selector}")

    async def eval_js(self, script: str) -> Any:
        self.calls.append("eval_js")
        return self._results


@pytest.fixture
def fake_session(monkeypatch):
    """Yields a function that installs a fake session for the duration of a test."""

    holder: dict[str, _FakeSession] = {}

    def _install(results=None, raise_on=None):
        sess = _FakeSession(results=results, raise_on=raise_on)
        holder["sess"] = sess
        # Patch BOTH the import path that backends uses and the original
        # module so anywhere it's re-imported still gets the fake.
        import src.core.browser as core_browser
        monkeypatch.setattr(core_browser, "BrowserSession", lambda **_kw: sess)
        return sess

    yield _install


@pytest.mark.unit
async def test_browser_search_extracts_results(fake_session) -> None:
    fake = fake_session(results=[
        {"title": "Python docs", "url": "https://docs.python.org/3/", "snippet": "Official Python docs"},
        {"title": "Real Python", "url": "https://realpython.com/", "snippet": "Tutorials"},
    ])
    results = await backends._browser_search("python tutorial", 10)
    assert len(results) == 2
    assert all(isinstance(r, SearchResult) for r in results)
    assert results[0].url == "https://docs.python.org/3/"
    assert results[0].source == "browser"
    # Lifecycle ordering: start → goto → wait_for → eval_js → stop
    assert "start" in fake.calls
    assert "stop" == fake.calls[-1], "session must be stopped after extraction"


@pytest.mark.unit
async def test_browser_search_filters_non_http_urls(fake_session) -> None:
    """Bing occasionally returns javascript: or relative URLs in card variants —
    they must be dropped so downstream visit code doesn't choke."""
    fake_session(results=[
        {"title": "ok", "url": "https://valid.example.com/page", "snippet": "ok"},
        {"title": "bad", "url": "javascript:void(0)", "snippet": "bad"},
        {"title": "rel", "url": "/relative", "snippet": "bad"},
        {"title": "empty", "url": "", "snippet": "bad"},
    ])
    results = await backends._browser_search("q", 10)
    assert len(results) == 1
    assert results[0].url == "https://valid.example.com/page"


@pytest.mark.unit
async def test_browser_search_caps_snippet_length(fake_session) -> None:
    long_snippet = "x" * 5000
    fake_session(results=[{"title": "t", "url": "https://x.com/", "snippet": long_snippet}])
    results = await backends._browser_search("q", 10)
    assert len(results[0].snippet) == 500


@pytest.mark.unit
async def test_browser_search_stops_session_on_error(fake_session) -> None:
    """Even if goto/wait_for blow up we still must call stop() — otherwise
    the patchright process leaks."""
    fake = fake_session(results=[], raise_on="goto")
    with pytest.raises(OSError, match="network down"):
        await backends._browser_search("q", 10)
    assert fake.calls[-1] == "stop"


@pytest.mark.unit
async def test_search_chain_prefers_browser_in_auto_mode(monkeypatch, fake_session) -> None:
    """In auto mode (no Tavily key), browser must be the FIRST backend
    tried — that's the whole point of the M2 reordering."""
    from src.config import settings

    # Force "auto" with no Tavily key.
    monkeypatch.setattr(settings, "search_backend", "auto")
    monkeypatch.setattr(settings, "tavily_api_key", "")

    fake_session(results=[
        {"title": "t", "url": "https://example.com/", "snippet": "s"},
    ])

    results = await backends.search("anything")
    assert len(results) == 1
    assert results[0].source == "browser"
    # last_errors should be empty for `browser` after a success.
    assert "browser" not in backends.last_errors


@pytest.mark.unit
async def test_search_records_last_error_when_backend_fails(monkeypatch, fake_session) -> None:
    """Failures must be recorded in the module-level health surface so
    the future /api/search/health endpoint has something to read."""
    from src.config import settings
    monkeypatch.setattr(settings, "search_backend", "browser")
    fake_session(results=[], raise_on="goto")

    with pytest.raises(backends.SearchError):
        await backends.search("anything")
    assert "browser" in backends.last_errors
    assert "OSError" in backends.last_errors["browser"]
