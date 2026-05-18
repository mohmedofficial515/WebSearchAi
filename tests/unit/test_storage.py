"""Unit tests for persistent task storage."""
from __future__ import annotations
import pytest
import time

from src.storage.store import TaskStore


@pytest.fixture
async def store(tmp_path):
    s = TaskStore(str(tmp_path / "tasks.db"))
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_save_and_load_task(store):
    await store.save_task("t1", "run", {"goal": "test"}, "queued")
    task = await store.load_task("t1")
    assert task is not None
    assert task["task_id"] == "t1"
    assert task["kind"] == "run"
    assert task["params"]["goal"] == "test"
    assert task["status"] == "queued"


@pytest.mark.asyncio
async def test_update_status(store):
    await store.save_task("t2", "explore", {"site_url": "https://x.com"}, "queued")
    await store.update_status("t2", "succeeded", result={"features": 5})
    task = await store.load_task("t2")
    assert task["status"] == "succeeded"
    assert task["result"]["features"] == 5


@pytest.mark.asyncio
async def test_update_status_with_error(store):
    await store.save_task("t3", "run", {}, "running")
    await store.update_status("t3", "failed", error="timeout after 30s")
    task = await store.load_task("t3")
    assert task["status"] == "failed"
    assert "timeout" in task["error"]


@pytest.mark.asyncio
async def test_list_tasks_ordered_by_created(store):
    await store.save_task("t4", "run", {}, "queued")
    await store.save_task("t5", "run", {}, "queued")
    tasks = await store.list_tasks()
    ids = [t["task_id"] for t in tasks]
    assert "t4" in ids
    assert "t5" in ids


@pytest.mark.asyncio
async def test_list_tasks_filter_by_kind(store):
    await store.save_task("t6", "run", {}, "queued")
    await store.save_task("t7", "explore", {}, "queued")
    runs = await store.list_tasks(kind="run")
    assert all(t["kind"] == "run" for t in runs)
    assert not any(t["task_id"] == "t7" for t in runs)


@pytest.mark.asyncio
async def test_delete_task(store):
    await store.save_task("t8", "run", {}, "queued")
    await store.delete_task("t8")
    assert await store.load_task("t8") is None


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none(store):
    result = await store.load_task("nonexistent-id")
    assert result is None
