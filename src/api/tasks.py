"""Background task manager with SQLite persistence."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List

from ..utils.event_bus import Event, bus
from ..utils.logger import log


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskOutcome(str, Enum):
    """Honest report of *what the task produced*, orthogonal to TaskStatus.

    A task can be `status=SUCCEEDED` (the runner didn't raise) and still
    have produced nothing useful — the previous design conflated the two
    and gave users a green check on empty results. The frontend renders
    a different visual state for each outcome (OK → green, NO_RESULTS →
    amber, *_ERROR → red).
    """
    OK = "ok"                          # genuine answer with sources
    NO_RESULTS = "no_results"          # search returned 0 usable sources
    PARTIAL = "partial"                # found some sources but synthesis was weak
    SEARCH_FAILED = "search_failed"    # all search backends threw
    SYNTHESIS_ERROR = "synthesis_error"  # LLM synthesis call failed


@dataclass
class TaskRecord:
    task_id: str
    kind: str
    params: dict[str, Any]
    status: TaskStatus = TaskStatus.QUEUED
    result: Any | None = None
    error: str | None = None
    # outcome / outcome_reason are populated by the runner when the wrapped
    # function (typically an Agent.run) returns a result with `.outcome`
    # set. Older skill calls won't set them — that's fine; the UI treats
    # `outcome=None` as OK so existing flows are unaffected.
    outcome: TaskOutcome | None = None
    outcome_reason: str | None = None
    asyncio_task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "params": self.params,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "outcome": self.outcome.value if self.outcome else None,
            "outcome_reason": self.outcome_reason,
        }


async def _persist_save(task_id: str, kind: str, params: dict, status: str) -> None:
    try:
        from ..storage import get_task_store
        store = await get_task_store()
        await store.save_task(task_id, kind, params, status)
    except Exception:  # noqa: BLE001 — sqlite/disk errors must not break task scheduling
        log.exception("Task persist save failed (task_id=%s)", task_id)


async def _persist_update(
    task_id: str, status: str, result: dict | None = None, error: str | None = None
) -> None:
    try:
        from ..storage import get_task_store
        store = await get_task_store()
        await store.update_status(task_id, status, result=result, error=error)
    except Exception:  # noqa: BLE001 — sqlite/disk errors must not break task scheduling
        log.exception("Task persist update failed (task_id=%s)", task_id)


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def list(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    async def list_history(self, limit: int = 100, kind: str | None = None) -> List[Dict[str, Any]]:
        """Return tasks from the persistent DB (includes completed/past-session tasks)."""
        try:
            from ..storage import get_task_store
            store = await get_task_store()
            return await store.list_tasks(limit=limit, kind=kind)
        except Exception:  # noqa: BLE001 — fall back to empty history when DB is unavailable
            log.exception("Task history load failed")
            return []

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def submit(
        self,
        kind: str,
        params: dict[str, Any],
        coro_factory: Callable[[str], Awaitable[Any]],
    ) -> TaskRecord:
        task_id = uuid.uuid4().hex[:10]
        record = TaskRecord(task_id=task_id, kind=kind, params=params)
        self._tasks[task_id] = record

        async def _runner() -> None:
            record.status = TaskStatus.RUNNING
            await bus.publish(Event(task_id=task_id, type="status",
                                    data={"status": record.status.value}))
            await _persist_save(task_id, kind, params, TaskStatus.RUNNING.value)
            try:
                result = await coro_factory(task_id)
                # Pull outcome metadata off the raw object (TaskResult) BEFORE
                # we coerce to dict — the dataclass-to-dict step drops attrs
                # that aren't part of `to_dict()`.
                _outcome = getattr(result, "outcome", None)
                _outcome_reason = getattr(result, "outcome_reason", None)
                if isinstance(_outcome, TaskOutcome):
                    record.outcome = _outcome
                elif isinstance(_outcome, str):
                    try:
                        record.outcome = TaskOutcome(_outcome)
                    except ValueError:
                        # Unknown outcome string from a downstream skill — keep
                        # it visible in the reason so we can debug.
                        record.outcome_reason = (
                            f"unknown-outcome={_outcome!r}; {_outcome_reason or ''}"
                        ).strip("; ")
                if _outcome_reason and record.outcome_reason is None:
                    record.outcome_reason = str(_outcome_reason)

                record.result = (
                    result.to_dict() if hasattr(result, "to_dict") else result
                )
                record.status = TaskStatus.SUCCEEDED
                await _persist_update(task_id, TaskStatus.SUCCEEDED.value, result=record.result)
            except asyncio.CancelledError:
                record.status = TaskStatus.CANCELLED
                await _persist_update(task_id, TaskStatus.CANCELLED.value)
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("task failed")
                record.error = f"{type(e).__name__}: {e}"
                record.status = TaskStatus.FAILED
                await _persist_update(task_id, TaskStatus.FAILED.value, error=record.error)
            finally:
                await bus.publish(
                    Event(
                        task_id=task_id,
                        type="status",
                        data={
                            "status": record.status.value,
                            "error": record.error,
                            "result": record.result,
                            "outcome": record.outcome.value if record.outcome else None,
                            "outcome_reason": record.outcome_reason,
                        },
                    )
                )

        record.asyncio_task = asyncio.create_task(_runner())
        return record

    def cancel(self, task_id: str) -> bool:
        rec = self._tasks.get(task_id)
        if not rec or not rec.asyncio_task or rec.asyncio_task.done():
            return False
        rec.asyncio_task.cancel()
        return True


task_manager = TaskManager()
