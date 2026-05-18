"""Pipeline + completion-prompt event types.

The event bus (src/utils/event_bus.py) is type-agnostic: events are just
`{task_id, type, data}`. This module pins the *names* and *payload shapes*
of the events the orchestrator emits, so the React frontend and backend
agree on the wire format without scattering string literals.

See CHAT_UI_PLAN §10.5 for the full shapes — the docstrings below match.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


# ── Event type constants ────────────────────────────────────────────────────

PIPELINE_PLAN = "pipeline_plan"
PIPELINE_APPROVED = "pipeline_approved"
PIPELINE_STEP_START = "pipeline_step_start"
PIPELINE_STEP_END = "pipeline_step_end"
PIPELINE_PAUSED = "pipeline_paused"
PIPELINE_RESUMED = "pipeline_resumed"
PIPELINE_END = "pipeline_end"
COMPLETION_PROMPT = "completion_prompt"

ALL_PIPELINE_EVENTS: tuple[str, ...] = (
    PIPELINE_PLAN,
    PIPELINE_APPROVED,
    PIPELINE_STEP_START,
    PIPELINE_STEP_END,
    PIPELINE_PAUSED,
    PIPELINE_RESUMED,
    PIPELINE_END,
    COMPLETION_PROMPT,
)


# ── Payload shapes ──────────────────────────────────────────────────────────

class RequiredField(TypedDict, total=False):
    """One required field surfaced in a pipeline_paused event."""
    name: str
    label_ar: str
    type: Literal["text", "url", "email", "password", "select"]
    required: bool
    options: list[str]
    placeholder: str


class PipelineStepData(TypedDict, total=False):
    step_id: str
    skill: str
    label_ar: str
    params: dict[str, Any]
    status: str
    result: Any
    error: str


class PipelinePlanData(TypedDict):
    pipeline_id: str
    goal: str
    summary_ar: str
    needs_approval: bool
    steps: list[PipelineStepData]


class PipelinePausedData(TypedDict):
    pipeline_id: str
    step_id: str
    required_fields: list[RequiredField]


class CompletionPromptData(TypedDict):
    task_or_pipeline_id: str
    suggestions: list[dict[str, str]]  # [{label_ar, prompt}, ...]
