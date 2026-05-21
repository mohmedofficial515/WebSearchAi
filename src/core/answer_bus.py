"""Answer bus — lets a running skill pause and wait for a user answer.

Usage (inside a skill coroutine):
    from ..core.answer_bus import register, wait_answer
    register(task_id)
    await bus.publish(Event(task_id=task_id, type="agent_question", data={...}))
    answer = await wait_answer(task_id, timeout=120.0)

Usage (from the API route that receives the answer):
    from ...core.answer_bus import post_answer
    ok = post_answer(task_id, {"value": ...})
"""

from __future__ import annotations

import asyncio

_events: dict[str, asyncio.Event] = {}
_answers: dict[str, dict] = {}


def register(task_id: str) -> None:
    """Reserve a slot — must be called before publishing agent_question."""
    _events[task_id] = asyncio.Event()
    _answers.pop(task_id, None)


async def wait_answer(task_id: str, timeout: float = 120.0) -> dict | None:
    """Block until the user submits an answer or timeout expires."""
    ev = _events.get(task_id)
    if not ev:
        return None
    try:
        await asyncio.wait_for(asyncio.shield(ev.wait()), timeout=timeout)
        return _answers.pop(task_id, {})
    except asyncio.TimeoutError:
        return None
    finally:
        _events.pop(task_id, None)


def post_answer(task_id: str, data: dict) -> bool:
    """Called by the /answer HTTP route. Returns False if no one is waiting."""
    ev = _events.get(task_id)
    if not ev:
        return False
    _answers[task_id] = data
    ev.set()
    return True
