"""GET /api/continuation/{task_or_pipeline_id} — completion follow-ups.

After a task/pipeline ends, the ContinuationCard offers 3 suggested
next-step prompts. We pre-compute them asynchronously with a 2-second
timeout: if the LLM is slow we return an empty list and the card simply
shows without suggestions (G18 fix).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...config import settings
from ...core.prompt_loader import load_prompt
from ...llm.providers import get_provider
from ...utils.event_bus import bus
from ..tasks import task_manager


router = APIRouter(prefix="/api", tags=["continuation"])


class Suggestion(BaseModel):
    label_ar: str
    prompt: str


class ContinuationResponse(BaseModel):
    suggestions: list[Suggestion] = Field(default_factory=list)


def _gather_context(task_or_pipeline_id: str) -> tuple[str, str, str]:
    """Returns (goal, summary, skill) — best-effort across both the live
    TaskManager and the event-bus history."""
    rec = task_manager.get(task_or_pipeline_id)
    if rec is not None:
        goal = str(rec.params.get("goal") or rec.params.get("message") or "")
        summary = ""
        if isinstance(rec.result, dict):
            summary = str(
                rec.result.get("summary")
                or rec.result.get("final_message_ar")
                or ""
            )[:600]
        return goal, summary, rec.kind

    # Fall back to event-bus history for pipeline ids.
    events = bus.history(task_or_pipeline_id)
    goal = ""
    summary = ""
    skill = "pipeline"
    for ev in events:
        if ev.type == "pipeline_plan":
            goal = str(ev.data.get("goal") or "")
        if ev.type == "pipeline_end":
            results = ev.data.get("results") or {}
            if isinstance(results, dict) and results:
                last = list(results.values())[-1]
                if isinstance(last, dict):
                    summary = str(last.get("summary") or "")[:600]
    return goal, summary, skill


@router.get(
    "/continuation/{task_or_pipeline_id}",
    response_model=ContinuationResponse,
)
async def continuation(task_or_pipeline_id: str, locale: str = "ar") -> ContinuationResponse:
    goal, summary, skill = _gather_context(task_or_pipeline_id)
    if not goal and not summary:
        return ContinuationResponse(suggestions=[])

    system = load_prompt("continuation", locale=locale)
    user = (
        f"GOAL: {goal}\n\nSUMMARY:\n{summary or '(empty)'}\n\nSKILL: {skill}"
    )

    try:
        llm = get_provider(settings)
    except Exception:
        return ContinuationResponse(suggestions=[])

    try:
        data: Any = await asyncio.wait_for(llm.chat_json(system, user), timeout=2.0)
    except asyncio.TimeoutError:
        return ContinuationResponse(suggestions=[])
    except Exception:
        return ContinuationResponse(suggestions=[])
    finally:
        try:
            await llm.close()
        except Exception:
            pass

    raw = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return ContinuationResponse(suggestions=[])
    cleaned: list[Suggestion] = []
    for s in raw[:5]:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label_ar") or "").strip()
        prompt = str(s.get("prompt") or "").strip()
        if label and prompt:
            cleaned.append(Suggestion(label_ar=label, prompt=prompt))
    return ContinuationResponse(suggestions=cleaned[:3])
