"""Event bus pub/sub behavior."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.unit
async def test_publish_subscribe_roundtrip():
    from src.utils.event_bus import Event, EventBus

    bus = EventBus()
    q = bus.subscribe("task-1")

    await bus.publish(Event(task_id="task-1", type="plan", data={"goal": "x"}))
    await bus.publish(Event(task_id="task-1", type="task_end", data={"ok": True}))

    e1 = await asyncio.wait_for(q.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q.get(), timeout=1.0)
    assert e1.type == "plan"
    assert e2.type == "task_end"


@pytest.mark.unit
async def test_subscribe_filters_by_task_id():
    from src.utils.event_bus import Event, EventBus

    bus = EventBus()
    target_q = bus.subscribe("target")

    await bus.publish(Event(task_id="other", type="plan", data={}))
    await bus.publish(Event(task_id="target", type="task_end", data={}))

    evt = await asyncio.wait_for(target_q.get(), timeout=1.0)
    assert evt.task_id == "target"
    assert evt.type == "task_end"
    # The "other" event must not have leaked into target's queue
    assert target_q.empty()


@pytest.mark.unit
async def test_subscriber_receives_history_on_attach():
    """Late subscribers should still receive events published before they joined."""
    from src.utils.event_bus import Event, EventBus

    bus = EventBus()
    await bus.publish(Event(task_id="t1", type="plan", data={}))
    await bus.publish(Event(task_id="t1", type="decision", data={}))

    q = bus.subscribe("t1")  # subscribes AFTER both publishes
    e1 = await asyncio.wait_for(q.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q.get(), timeout=1.0)
    assert e1.type == "plan"
    assert e2.type == "decision"


@pytest.mark.unit
async def test_history_returns_all_events():
    from src.utils.event_bus import Event, EventBus

    bus = EventBus()
    await bus.publish(Event(task_id="t", type="a", data={}))
    await bus.publish(Event(task_id="t", type="b", data={}))

    h = bus.history("t")
    assert [e.type for e in h] == ["a", "b"]
