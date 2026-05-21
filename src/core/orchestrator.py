"""Multi-skill pipeline orchestrator.

Given a compound user message, the orchestrator:
  1. Decides whether it's actually compound (cheap heuristic, then LLM
     fallback at the caller's discretion).
  2. Plans a sequence of skill invocations as a Pipeline.
  3. Executes them step-by-step, resolving `$sN.field` references against
     prior step results.
  4. Streams pipeline-level events through the existing event bus so the
     React chat UI can render a live PipelineCard.

The orchestrator does NOT execute skills directly — it takes a `step_runner`
callable that the caller provides (the API layer wires this to TaskManager).
That keeps the orchestrator pure and testable: unit tests provide a mock
runner that returns canned step results.

Public surface:
    orch = Orchestrator(llm, step_runner=...)
    is_compound = orch.is_compound_heuristic(message)
    pipeline    = await orch.plan(message, locale="ar")
    async for event in orch.run(pipeline, pipeline_id):
        ...   # caller publishes to event bus
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable

from .pipeline_events import (
    PIPELINE_END,
    PIPELINE_PAUSED,
    PIPELINE_PLAN,
    PIPELINE_STEP_END,
    PIPELINE_STEP_START,
)
from .prompt_loader import load_prompt


# Pipelines are not free — every step is a real skill call. The orchestrator
# caps fan-out to keep cost/load predictable; anything past the cap queues.
FAN_OUT_CAP = 5

# Heuristic: messages with multiple clauses (separated by Arabic/English
# conjunctions or punctuation) AND that contain at least one verb-like
# token are LIKELY compound. We're intentionally permissive — the cheap
# heuristic just decides whether to escalate to an LLM compound check.
_COMPOUND_CONJUNCTIONS = (
    " ثم ", " وبعدها ", " وأيضًا ", " وايضا ",
    " then ", " and then ", " after that ", " also ",
)
_CLAUSE_SPLITTERS = re.compile(r"[،,؛;.!?]+|\bثم\b|\bو\s|\band\b|\bthen\b", re.IGNORECASE)

# Match `$sN.field.subfield` references emitted by the planner.
_REF_RE = re.compile(r"^\$s(\d+)((?:\.[\w]+)*)$")
# Sentinel that means "this param needs user input before the step can run".
_ASK_USER = "$askUser"


@dataclass
class PipelineStep:
    """A single skill invocation inside a pipeline."""
    step_id: str
    skill: str
    label_ar: str
    params: dict[str, Any] = field(default_factory=dict)
    fan_out: dict[str, Any] | None = None
    required_fields: list[dict[str, Any]] = field(default_factory=list)
    # Filled at runtime.
    status: str = "pending"          # pending | running | succeeded | failed | paused
    result: Any | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "skill": self.skill,
            "label_ar": self.label_ar,
            "params": self.params,
            "fan_out": self.fan_out,
            "required_fields": self.required_fields,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class Pipeline:
    """A planned multi-step pipeline. Frozen after plan() — execution
    updates step.status / step.result in place."""
    pipeline_id: str
    goal: str
    summary_ar: str
    needs_approval: bool
    steps: list[PipelineStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "goal": self.goal,
            "summary_ar": self.summary_ar,
            "needs_approval": self.needs_approval,
            "steps": [s.to_dict() for s in self.steps],
        }

    def step_by_id(self, step_id: str) -> PipelineStep | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None


# A step runner takes (skill, params, on_task_id_callback) and returns the
# skill's result dict.  The callback is called synchronously with the
# backend task_id as soon as the task is dispatched (before it completes),
# so the orchestrator can include task_id in PIPELINE_STEP_START.
TaskIdCallback = Callable[[str], None]
StepRunner = Callable[[str, dict[str, Any], TaskIdCallback | None], Awaitable[dict[str, Any]]]


class Orchestrator:
    def __init__(
        self,
        llm: Any,
        *,
        step_runner: StepRunner,
        available_skills: list[dict[str, str]] | None = None,
        locale: str = "ar",
    ) -> None:
        self._llm = llm
        self._step_runner = step_runner
        self._skills = available_skills or _DEFAULT_SKILLS
        self.locale = locale

    # ── Compound detection ────────────────────────────────────────────────

    def is_compound_heuristic(self, message: str) -> bool:
        """Cheap regex/clause-count check. Returns True when the message
        looks like a multi-step goal.

        Not authoritative — the caller may still escalate to an LLM call
        when confidence is in the gray zone. False positives are fine here
        because the LLM check will reject them; false negatives are the
        risk we minimize.
        """
        m = (message or "").strip()
        if not m:
            return False
        # Explicit conjunctions almost always mean "do X, then Y".
        low = " " + m.lower() + " "
        for c in _COMPOUND_CONJUNCTIONS:
            if c in low:
                return True
        # Multiple non-trivial clauses → probably compound.
        clauses = [c.strip() for c in _CLAUSE_SPLITTERS.split(m) if c.strip()]
        # We use a small min-length filter so "ابحث،" or "go." don't count.
        meaningful = [c for c in clauses if len(c) >= 6]
        return len(meaningful) >= 2

    # ── Planning ──────────────────────────────────────────────────────────

    async def plan(
        self,
        message: str,
        *,
        locale: str | None = None,
        history: list[dict] | None = None,
    ) -> Pipeline:
        """LLM-plan a pipeline for a (presumed compound) message.

        On any planner failure we degrade to a single-step "research"
        pipeline so the caller always gets a runnable plan.
        """
        loc = locale or self.locale
        system = load_prompt("orchestrator", locale=loc)
        skills_block = "\n".join(
            f"- {s['name']}: {s.get('description', '')}" for s in self._skills
        )
        history_block = ""
        if history:
            history_block = "CONVERSATION HISTORY (most recent last):\n"
            for msg in history[-10:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = (msg.get("content") or "")[:400]
                history_block += f"{role}: {content}\n"
            history_block += "\n"
        user = f"{history_block}USER MESSAGE:\n{message}\n\nAVAILABLE SKILLS:\n{skills_block}"

        data: dict[str, Any] = {}
        try:
            raw = await self._llm.chat_json(system, user)
            if isinstance(raw, dict):
                data = raw
        except Exception:
            data = {}

        steps_raw = data.get("steps") if isinstance(data.get("steps"), list) else []
        steps: list[PipelineStep] = []
        for i, sd in enumerate(steps_raw, start=1):
            if not isinstance(sd, dict) or not sd.get("skill"):
                continue
            step_id = str(sd.get("step_id") or f"s{i}")
            fan_out = sd.get("fan_out") if isinstance(sd.get("fan_out"), dict) else None
            req = sd.get("required_fields") or []
            if not isinstance(req, list):
                req = []
            steps.append(PipelineStep(
                step_id=step_id,
                skill=str(sd["skill"]),
                label_ar=str(sd.get("label_ar") or sd["skill"]),
                params=dict(sd.get("params") or {}),
                fan_out=fan_out,
                required_fields=req,
            ))

        if not steps:
            # Degrade gracefully — a one-step research pipeline always
            # beats erroring out on a parse failure.
            steps = [PipelineStep(
                step_id="s1",
                skill="research",
                label_ar="البحث",
                params={"goal": message},
            )]
            data.setdefault("summary_ar", "تشغيل بحث على الرسالة")
            data.setdefault("needs_approval", False)

        summary = str(data.get("summary_ar") or "")
        critique = str(data.get("critique_ar") or "")
        # Append critique to summary so the UI surfaces it without new fields.
        if critique and critique not in summary:
            summary = f"{summary} — {critique}" if summary else critique

        return Pipeline(
            pipeline_id=uuid.uuid4().hex,
            goal=message,
            summary_ar=summary,
            needs_approval=bool(data.get("needs_approval", len(steps) >= 3)),
            steps=steps,
        )

    # ── Param resolution ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_params(
        params: dict[str, Any],
        results: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """Resolve `$sN.field` references and detect `$askUser` sentinels.

        Returns (resolved_params, missing_param_keys). When the latter is
        non-empty the caller must pause the pipeline for user input.
        """
        missing: list[str] = []
        out: dict[str, Any] = {}
        for k, v in params.items():
            if isinstance(v, str):
                if v == _ASK_USER:
                    missing.append(k)
                    out[k] = None
                    continue
                m = _REF_RE.match(v)
                if m:
                    step_idx = int(m.group(1))
                    path = [p for p in m.group(2).split(".") if p]
                    out[k] = _walk(results.get(f"s{step_idx}"), path)
                    continue
            out[k] = v
        return out, missing

    # ── Execution ─────────────────────────────────────────────────────────

    async def run(
        self,
        pipeline: Pipeline,
        user_inputs: dict[str, dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute the pipeline sequentially. Yields event-bus payloads.

        Each yielded value is a `{type, data}` dict. The caller is
        responsible for publishing them to the bus with the right
        task_id / pipeline_id correlation.

        `user_inputs` maps step_id → filled-in `$askUser` params. When a
        step has unresolved `$askUser` params and no override is supplied,
        the runner yields a `pipeline_paused` event and stops; the caller
        re-invokes `run()` with the input filled in.
        """
        user_inputs = user_inputs or {}
        results: dict[str, Any] = {}

        yield {"type": PIPELINE_PLAN, "data": pipeline.to_dict()}

        for step in pipeline.steps:
            # Merge any user-supplied inputs for this step.
            if step.step_id in user_inputs:
                step.params = {**step.params, **user_inputs[step.step_id]}

            resolved, missing = self._resolve_params(step.params, results)
            if missing:
                step.status = "paused"
                yield {
                    "type": PIPELINE_PAUSED,
                    "data": {
                        "pipeline_id": pipeline.pipeline_id,
                        "step_id": step.step_id,
                        "required_fields": [
                            _field_schema(step, name) for name in missing
                        ],
                    },
                }
                return

            step.status = "running"

            # Collect task_id as soon as the backend dispatches it (before it
            # completes) so the frontend can subscribe to its WS stream for
            # live in-step progress.
            task_id_holder: list[str] = []

            def _on_task_id(tid: str) -> None:
                task_id_holder.append(tid)

            # Start the step as a Task so we can yield PIPELINE_STEP_START
            # (which needs task_id) after the dispatch is recorded but before
            # the actual work completes.
            step_task = asyncio.ensure_future(
                self._fan_out(step, resolved, results, _on_task_id)
                if step.fan_out
                else self._step_runner(step.skill, resolved, _on_task_id)
            )
            # Yield control so the task coroutine runs until its first
            # internal await, at which point the synchronous dispatch has
            # already fired and _on_task_id has been called.
            await asyncio.sleep(0)

            yield {
                "type": PIPELINE_STEP_START,
                "data": {
                    "pipeline_id": pipeline.pipeline_id,
                    "step_id": step.step_id,
                    "skill": step.skill,
                    "label_ar": step.label_ar,
                    "params": resolved,
                    "task_id": task_id_holder[0] if task_id_holder else "",
                },
            }

            try:
                step_result = await step_task
                step.status = "succeeded"
                step.result = step_result
                results[step.step_id] = step_result
                yield {
                    "type": PIPELINE_STEP_END,
                    "data": {
                        "pipeline_id": pipeline.pipeline_id,
                        "step_id": step.step_id,
                        "status": "done",
                        "result": step_result,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                step.status = "failed"
                step.error = f"{type(exc).__name__}: {exc}"
                yield {
                    "type": PIPELINE_STEP_END,
                    "data": {
                        "pipeline_id": pipeline.pipeline_id,
                        "step_id": step.step_id,
                        "status": "failed",
                        "error": step.error,
                    },
                }
                yield {
                    "type": PIPELINE_END,
                    "data": {
                        "pipeline_id": pipeline.pipeline_id,
                        "status": "failed",
                        "summary_ar": f"فشل في الخطوة: {step.label_ar}",
                        "failed_step": step.step_id,
                    },
                }
                return

        all_summaries = " → ".join(
            str((r.get("summary_ar") or r.get("summary") or "")[:60])
            for r in results.values()
            if isinstance(r, dict)
        )
        yield {
            "type": PIPELINE_END,
            "data": {
                "pipeline_id": pipeline.pipeline_id,
                "status": "done",
                "summary_ar": all_summaries or "اكتملت جميع الخطوات بنجاح",
                "results": {sid: r for sid, r in results.items()},
            },
        }

    async def _fan_out(
        self,
        step: PipelineStep,
        resolved: dict[str, Any],
        results: dict[str, Any],
        on_task_id: TaskIdCallback | None = None,
    ) -> list[Any]:
        """Run the step's skill once per item from `fan_out.over`.

        `fan_out = {"over": "$s1.results", "param": "url"}` means: for each
        element of step s1's `results`, run the skill with `param=<element>`
        plus the other resolved params. Concurrent execution is capped at
        FAN_OUT_CAP; the rest queue up.
        """
        spec = step.fan_out or {}
        over_ref = str(spec.get("over") or "")
        param_name = str(spec.get("param") or "")
        items: list[Any] = []
        m = _REF_RE.match(over_ref)
        if m:
            items = _walk(results.get(f"s{int(m.group(1))}"), [p for p in m.group(2).split(".") if p]) or []
        if not isinstance(items, list):
            items = []

        sem = asyncio.Semaphore(FAN_OUT_CAP)
        first_cb_done = False

        async def _one(item: Any) -> Any:
            nonlocal first_cb_done
            async with sem:
                child_params = {**resolved, param_name: item}
                # Only fire the callback once (for the first parallel item).
                cb = on_task_id if not first_cb_done else None
                first_cb_done = True
                return await self._step_runner(step.skill, child_params, cb)

        return await asyncio.gather(*[_one(it) for it in items], return_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _walk(value: Any, path: list[str]) -> Any:
    """Walk a dotted path through dicts/lists. Returns None on miss."""
    cur: Any = value
    for p in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _field_schema(step: PipelineStep, param_name: str) -> dict[str, Any]:
    """Look up the planner-supplied required-field schema for `param_name`,
    falling back to a minimal shape if the planner didn't provide one."""
    for r in step.required_fields:
        if isinstance(r, dict) and r.get("name") == param_name:
            return r
    return {
        "name": param_name,
        "label_ar": param_name,
        "type": "text",
        "required": True,
    }


# Minimal skill catalog the orchestrator advertises to the planner LLM. The
# real registry lives in `src/skills/plugin_loader.py`; we keep a short
# string-based catalog here to avoid an import cycle.
_DEFAULT_SKILLS: list[dict[str, str]] = [
    {"name": "research", "description": "Web research with cited Arabic answer."},
    {"name": "explore", "description": "Explore a website and write a feature report."},
    {"name": "clone", "description": "Clone a page as clean Tailwind HTML."},
    {"name": "site_clone", "description": "Crawl a whole site and download its HTML."},
    {"name": "find_components", "description": "Search the web for UI components and build a gallery."},
    {"name": "design_tokens", "description": "Extract colors/typography/spacing from a URL."},
    {"name": "html_artifact", "description": "Create or redesign a complete professional HTML page from a text description. No URL required — just describe the page goal including any research results from earlier steps. Use for any task that creates, builds, or updates an HTML design page (adding fonts, icons, images, layouts, etc.)."},
    {"name": "login", "description": "Log into a site with email + password."},
    {"name": "signup", "description": "Sign up on a site with a disposable email."},
    {"name": "temp_signup", "description": "Sign up with persistent browser profile."},
]
