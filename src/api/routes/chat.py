"""POST /api/chat — the unified chat endpoint.

Routes a user message to either:
  - a single skill task   (mode="single",   task_id)
  - a multi-skill pipeline (mode="pipeline", pipeline_id)
  - a parameter prompt    (mode="need_params", missing_params[])

Decision logic:
  1. Rule-based intent detect (fast).
  2. If the rule classifier picks a skill that needs params we lack
     (URL, credentials, etc.) → mode=need_params.
  3. If the compound heuristic AND the LLM confirm a multi-step goal →
     plan via Orchestrator → mode=pipeline.
  4. Otherwise → dispatch the single skill task → mode=single.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...config import settings
from ...core.intent_router import detect_intent
from ...core.orchestrator import Orchestrator, Pipeline
from ...llm.providers import get_provider
from ...utils.event_bus import Event, bus
from ...utils.logger import log
from ..tasks import task_manager


router = APIRouter(prefix="/api", tags=["chat"])


# ── Models ──────────────────────────────────────────────────────────────────


class ChatAttachment(BaseModel):
    attachment_id: str
    url: str
    mime: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    attachments: list[ChatAttachment] = Field(default_factory=list)
    # The composer can override the auto-detected skill — e.g. "force this
    # to run as `clone` even though intent picked `research`".
    force_skill: str | None = None
    # When the user approves an already-planned pipeline.
    approved_pipeline_id: str | None = None
    locale: str = "ar"


class ChatResponse(BaseModel):
    mode: Literal["single", "pipeline", "need_params"]
    task_id: str | None = None
    pipeline_id: str | None = None
    intent: str | None = None
    missing_params: list[str] | None = None
    pipeline: dict | None = None


# ── Pipeline registry — in-memory store for pending pipelines ──────────────


# We keep planned-but-not-approved pipelines in memory for the user's
# session. The lifecycle is short (plan → approve → run → drop); we don't
# bother with a persistent store yet.
_PIPELINES: dict[str, Pipeline] = {}


def remember_pipeline(p: Pipeline) -> None:
    _PIPELINES[p.pipeline_id] = p


def get_pipeline(pipeline_id: str) -> Pipeline | None:
    return _PIPELINES.get(pipeline_id)


def forget_pipeline(pipeline_id: str) -> None:
    _PIPELINES.pop(pipeline_id, None)


# ── Compound check ─────────────────────────────────────────────────────────


async def _llm_confirm_compound(message: str, llm: Any) -> bool:
    """Cheap LLM call to confirm/reject a borderline compound message.

    The heuristic is permissive; this LLM check filters its false
    positives. We give it a 3-second timeout — if the model is slow we
    just trust the heuristic and continue.
    """
    system = (
        "You decide whether a user message describes ONE atomic task or "
        "MULTIPLE chained tasks. Reply with JSON ONLY: "
        "{\"compound\": <bool>, \"reason\": \"<short>\"}"
    )
    try:
        data = await asyncio.wait_for(
            llm.chat_json(system, f"MESSAGE: {message}"),
            timeout=3.0,
        )
        return bool(isinstance(data, dict) and data.get("compound"))
    except Exception:
        return True  # heuristic already said compound — trust it on timeout


# ── Single-skill dispatch ───────────────────────────────────────────────────


def _dispatch_single(intent_kind: str, message: str, url: str | None,
                     params: dict[str, Any]) -> str:
    """Submit a single skill task via TaskManager. Returns task_id.

    Mirrors the dispatch logic in src/api/main.py::_dispatch_skill_intent —
    kept here so /api/chat doesn't import main.py (circular).
    """
    if intent_kind == "research":
        from ...core.agent import Agent

        async def _factory(_tid: str):
            async with Agent() as agent:
                return await agent.run(message, task_id=_tid)
        return task_manager.submit("run", {"goal": message}, _factory).task_id

    if intent_kind == "explore":
        from ...skills.explore import explore as _skill

        async def _factory(_tid: str):
            r = await _skill(url or "", params.get("depth_hint") or "thorough")
            return {"site": r.site, "report": r.report, "report_path": r.report_path}
        return task_manager.submit("explore", {"goal": message, "url": url}, _factory).task_id

    if intent_kind == "clone":
        from ...skills.clone import clone as _skill

        async def _factory(_tid: str):
            r = await _skill(url or "", max_assets=int(params.get("max_assets") or 60))
            return {
                "url": r.url, "raw_dir": r.raw_dir,
                "rebuilt_html_path": r.rebuilt_html_path, "assets": r.assets,
            }
        return task_manager.submit("clone", {"goal": message, "url": url}, _factory).task_id

    if intent_kind == "components":
        from ...skills.find_components import find_components

        async def _factory(_tid: str):
            r = await find_components(params.get("query") or message,
                                      max_pages=int(params.get("max_pages") or 5))
            return r.to_dict()
        return task_manager.submit("find_components", {"goal": message}, _factory).task_id

    if intent_kind == "design_tokens":
        from ...skills.design_tokens import extract_design_tokens

        async def _factory(_tid: str):
            t = await extract_design_tokens(url or "")
            return t.to_dict()
        return task_manager.submit("design_tokens", {"goal": message, "url": url}, _factory).task_id

    if intent_kind in {"login", "signup", "temp_signup"}:
        # These need credential fields — surfaced via missing_params upstream.
        # If we reach here the caller has them; mirror main.py dispatch.
        from ..main import _dispatch_skill_intent
        from ...core.intent_router import Intent

        # We use the existing main.py dispatcher which already handles
        # signup/login/temp_signup wiring correctly.
        rec = _dispatch_skill_intent(
            Intent(kind=intent_kind, goal=message, url=url, params=params, confidence=0.85),
            body=_FakeRunBody(),  # type: ignore[arg-type]
        )
        return rec.task_id

    # Default fallback — research.
    from ...core.agent import Agent

    async def _factory(_tid: str):
        async with Agent() as agent:
            return await agent.run(message, task_id=_tid)
    return task_manager.submit("run", {"goal": message}, _factory).task_id


class _FakeRunBody:
    """Minimal duck-typed shim so we can call main.py's _dispatch_skill_intent
    without depending on its full RunBody Pydantic model."""
    headless: bool | None = None
    use_vision: bool = True


# ── Pipeline step runner ────────────────────────────────────────────────────


async def _pipeline_step_runner(skill: str, params: dict[str, Any]) -> dict[str, Any]:
    """Run one pipeline step synchronously (inside the orchestrator's run())
    and wait for it to finish, then return its result dict.

    The orchestrator yields events; the API layer streams them through the
    pipeline's task_id channel on the event bus.
    """
    # We re-use _dispatch_single to get a task_id, then await its completion.
    # This makes pipeline steps fully observable on the existing /ws/<task_id>
    # channel — no new transport needed.
    intent_kind = skill
    url = params.get("url") or params.get("site_url")
    task_id = _dispatch_single(intent_kind, params.get("goal") or params.get("message") or "",
                               url, params)
    # Wait for the task to finish.
    while True:
        rec = task_manager.get(task_id)
        if rec is None:
            raise RuntimeError(f"task {task_id} disappeared mid-pipeline")
        if rec.status.value in {"succeeded", "failed", "cancelled"}:
            if rec.status.value != "succeeded":
                raise RuntimeError(rec.error or f"step {skill} failed")
            return rec.result if isinstance(rec.result, dict) else {"value": rec.result}
        await asyncio.sleep(0.2)


# ── Route ────────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    # ── 1. Approval branch: the user clicked ▶ on a planned pipeline ──
    if body.approved_pipeline_id:
        pipeline = get_pipeline(body.approved_pipeline_id)
        if pipeline is None:
            raise HTTPException(404, detail="الخطة غير موجودة أو منتهية الصلاحية")
        await _start_pipeline_run(pipeline)
        return ChatResponse(
            mode="pipeline",
            pipeline_id=pipeline.pipeline_id,
            pipeline=pipeline.to_dict(),
        )

    intent = detect_intent(body.message)
    kind = body.force_skill or intent.kind

    # ── 2. Missing-params check ────────────────────────────────────────
    missing: list[str] = []
    if kind in {"login", "explore", "clone", "design_tokens"} and not intent.url:
        missing.append("url")
    if kind == "login":
        for k in ("email", "password"):
            if not intent.params.get(k):
                missing.append(k)
    if missing:
        return ChatResponse(mode="need_params", intent=kind, missing_params=missing)

    # ── 3. Compound branch ────────────────────────────────────────────
    orch = Orchestrator(
        get_provider(settings),
        step_runner=_pipeline_step_runner,
        locale=body.locale,
    )
    if orch.is_compound_heuristic(body.message):
        try:
            confirmed = await _llm_confirm_compound(body.message, get_provider(settings))
        except Exception:
            confirmed = True  # fail-open: trust the heuristic
        if confirmed:
            try:
                pipeline = await orch.plan(body.message, locale=body.locale)
            except Exception as exc:  # noqa: BLE001
                log.warning(f"orchestrator.plan failed: {exc}")
                pipeline = None
            if pipeline and len(pipeline.steps) >= 2:
                remember_pipeline(pipeline)
                # If approval is not required, start running immediately.
                if not pipeline.needs_approval:
                    await _start_pipeline_run(pipeline)
                return ChatResponse(
                    mode="pipeline",
                    pipeline_id=pipeline.pipeline_id,
                    pipeline=pipeline.to_dict(),
                )

    # ── 4. Single-skill dispatch ──────────────────────────────────────
    try:
        task_id = _dispatch_single(kind, body.message, intent.url, dict(intent.params))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"تعذّر تشغيل المهارة: {exc}") from exc
    return ChatResponse(mode="single", task_id=task_id, intent=kind)


# ── Pipeline execution ──────────────────────────────────────────────────────


async def _start_pipeline_run(pipeline: Pipeline) -> None:
    """Kick off pipeline execution in the background, streaming events
    on the pipeline_id-keyed event-bus channel."""
    orch = Orchestrator(
        get_provider(settings),
        step_runner=_pipeline_step_runner,
    )

    async def _runner() -> None:
        try:
            async for ev in orch.run(pipeline):
                await bus.publish(Event(
                    task_id=pipeline.pipeline_id,
                    type=ev["type"],
                    data=ev["data"],
                ))
        except Exception as exc:  # noqa: BLE001
            log.exception("pipeline crashed")
            await bus.publish(Event(
                task_id=pipeline.pipeline_id,
                type="pipeline_end",
                data={"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            ))
        finally:
            forget_pipeline(pipeline.pipeline_id)

    asyncio.create_task(_runner())
