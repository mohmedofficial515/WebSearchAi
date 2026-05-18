"""In-process async pub/sub for streaming task progress to the Web UI."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    task_id: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    tab_id: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "type": self.type,
            "data": self.data,
            "ts": self.ts,
        }
        if self.tab_id is not None:
            d["tab_id"] = self.tab_id
        return d


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, list[Event]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(task_id, []).append(q)
        for ev in self._history.get(task_id, []):
            q.put_nowait(ev)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        if task_id in self._queues and q in self._queues[task_id]:
            self._queues[task_id].remove(q)

    async def publish(self, event: Event) -> None:
        self._history.setdefault(event.task_id, []).append(event)
        for q in self._queues.get(event.task_id, []):
            await q.put(event)

    def history(self, task_id: str) -> list[Event]:
        return list(self._history.get(task_id, []))


bus = EventBus()
