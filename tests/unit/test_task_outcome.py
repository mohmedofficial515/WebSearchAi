"""TaskOutcome wiring tests.

Covers the contract between Agent → TaskRecord:
  - TaskResult.outcome string is converted to TaskOutcome enum on the record
  - to_dict() exposes both fields
  - The "ok" outcome is the default for legacy tasks (None) so existing skill
    flows don't have to change.
  - The status event published at task end carries outcome + outcome_reason.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.api.tasks import TaskManager, TaskOutcome, TaskRecord, TaskStatus
from src.core.agent_helpers import TaskResult
from src.utils.event_bus import bus


@pytest.mark.unit
def test_task_record_to_dict_includes_outcome_fields() -> None:
    rec = TaskRecord(
        task_id="t1",
        kind="run",
        params={},
        outcome=TaskOutcome.NO_RESULTS,
        outcome_reason="no useful pages",
    )
    payload = rec.to_dict()
    assert payload["outcome"] == "no_results"
    assert payload["outcome_reason"] == "no useful pages"


@pytest.mark.unit
def test_task_record_default_outcome_is_none() -> None:
    """Legacy code that never sets outcome must keep working unchanged."""
    rec = TaskRecord(task_id="t1", kind="run", params={})
    assert rec.outcome is None
    payload = rec.to_dict()
    assert payload["outcome"] is None
    assert payload["outcome_reason"] is None


@pytest.mark.unit
def test_task_result_string_outcome_converted_to_enum() -> None:
    """Agent emits outcome as plain string (no core→api dep); manager
    converts it back to the enum at the boundary."""

    async def _run() -> None:
        tm = TaskManager()

        async def factory(_task_id: str) -> Any:
            return TaskResult(
                task_id="t-test",
                goal="g",
                success=True,
                confidence=1.0,
                reason="",
                summary="answer",
                outcome="no_results",
                outcome_reason="بحثنا في 0 رابط",
            )

        rec = tm.submit("run", {}, factory)
        await asyncio.wait_for(rec.asyncio_task, timeout=5.0)  # type: ignore[arg-type]
        assert rec.status == TaskStatus.SUCCEEDED
        assert rec.outcome == TaskOutcome.NO_RESULTS
        assert rec.outcome_reason == "بحثنا في 0 رابط"

    asyncio.run(_run())


@pytest.mark.unit
def test_unknown_outcome_string_logged_in_reason() -> None:
    """Defensive: if a downstream skill returns an outcome we don't know,
    we keep the original string visible in outcome_reason so we can debug
    instead of silently dropping it."""

    async def _run() -> None:
        tm = TaskManager()

        async def factory(_task_id: str) -> Any:
            return TaskResult(
                task_id="t-test",
                goal="g",
                success=True,
                confidence=1.0,
                reason="",
                summary="x",
                outcome="brand-new-state-we-have-not-defined-yet",
            )

        rec = tm.submit("run", {}, factory)
        await asyncio.wait_for(rec.asyncio_task, timeout=5.0)  # type: ignore[arg-type]
        assert rec.outcome is None  # we don't fabricate an enum value
        assert "unknown-outcome" in (rec.outcome_reason or "")

    asyncio.run(_run())


@pytest.mark.unit
def test_status_event_carries_outcome() -> None:
    """The final `status` event published on the event bus must include
    the outcome fields so the frontend can render the warning/error UI
    without polling /api/tasks."""

    async def _run() -> None:
        tm = TaskManager()
        received: list[dict[str, Any]] = []

        async def collector(task_id: str) -> None:
            q = bus.subscribe(task_id)
            try:
                # Pull events until we see the final status (succeeded/failed/cancelled)
                while True:
                    ev = await asyncio.wait_for(q.get(), timeout=2.0)
                    received.append({"type": ev.type, "data": ev.data})
                    if ev.type == "status" and ev.data.get("status") in (
                        "succeeded",
                        "failed",
                        "cancelled",
                    ):
                        return
            finally:
                bus.unsubscribe(task_id, q)

        async def factory(_task_id: str) -> Any:
            return TaskResult(
                task_id="t-test",
                goal="g",
                success=True,
                confidence=1.0,
                reason="",
                summary="",
                outcome="no_results",
                outcome_reason="explain",
            )

        rec = tm.submit("run", {}, factory)
        collect_task = asyncio.create_task(collector(rec.task_id))
        await asyncio.wait_for(rec.asyncio_task, timeout=5.0)  # type: ignore[arg-type]
        await asyncio.wait_for(collect_task, timeout=2.0)

        final = [e for e in received if e["type"] == "status" and e["data"].get("status") == "succeeded"]
        assert final, "no terminal status event was published"
        assert final[-1]["data"]["outcome"] == "no_results"
        assert final[-1]["data"]["outcome_reason"] == "explain"

    asyncio.run(_run())
