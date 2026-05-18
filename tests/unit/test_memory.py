"""Unit tests for the memory module (uses in-memory SQLite)."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch

from src.memory.store import MemoryStore
from src.memory.recall import MemoryRecall


@pytest.fixture
async def store(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_remember_and_recall_flow(store):
    await store.remember_flow(
        "https://github.com", "login", {"steps": ["goto", "fill_email", "fill_pass", "click_submit"]}
    )
    flow = await store.recall_flow("https://github.com", "login")
    assert flow is not None
    assert flow["flow_data"]["steps"][0] == "goto"


@pytest.mark.asyncio
async def test_forget_site_removes_everything(store):
    await store.remember_flow("https://example.com", "search", {"q": "test"})
    await store.remember_login("https://example.com", "/tmp/profile", "test@test.com")
    await store.forget_site("https://example.com")
    assert await store.recall_flow("https://example.com", "search") is None
    assert await store.recall_login("https://example.com") is None


@pytest.mark.asyncio
async def test_remember_login_profile(store):
    await store.remember_login("https://app.com", "/profiles/app", "user@app.com")
    profile = await store.recall_login("https://app.com")
    assert profile is not None
    assert profile["profile_path"] == "/profiles/app"
    assert profile["email"] == "user@app.com"


@pytest.mark.asyncio
async def test_list_sites(store):
    await store.remember_flow("https://a.com", "search", {})
    await store.remember_flow("https://b.com", "login", {})
    sites = await store.list_sites()
    urls = [s["url"] for s in sites]
    assert "https://a.com" in urls
    assert "https://b.com" in urls


@pytest.mark.asyncio
async def test_flow_success_count_increments(store):
    await store.remember_flow("https://x.com", "login", {"v": 1})
    await store.remember_flow("https://x.com", "login", {"v": 2})
    flow = await store.recall_flow("https://x.com", "login")
    assert flow["success_count"] == 2
    assert flow["flow_data"]["v"] == 2  # updated to latest


@pytest.mark.asyncio
async def test_recall_returns_none_for_unknown_site(store):
    result = await store.recall_flow("https://nonexistent.com", "login")
    assert result is None


@pytest.mark.asyncio
async def test_save_and_retrieve_vectors(store):
    embedding = [0.1, 0.2, 0.3]
    await store.save_vector("https://test.com", "test text", embedding, {"type": "flow"})
    vecs = await store.get_all_vectors()
    assert len(vecs) == 1
    assert vecs[0]["text"] == "test text"
    assert vecs[0]["embedding"] == embedding


@pytest.mark.asyncio
async def test_recall_search_returns_top_k(store):
    import math
    async def fake_embed(text):
        if "github" in text:
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    recall = MemoryRecall(store, "fake-key")
    recall._embed = fake_embed

    await recall.remember("https://github.com", "github repository code", {"site": "github"})
    await recall.remember("https://google.com", "search engine web", {"site": "google"})

    results = await recall.search("github code", k=2)
    assert results[0]["site_url"] == "https://github.com"
    assert results[0]["score"] > results[1]["score"]
