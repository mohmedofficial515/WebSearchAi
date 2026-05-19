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


async def _emit_skill_result(task_id: str, data: dict) -> None:
    """Emit a skill_result event so the frontend card can render rich data."""
    await bus.publish(Event(task_id=task_id, type="skill_result", data=data))


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
    # Frontend conversation ID — used for context tracking.
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    mode: Literal["single", "pipeline", "need_params", "chat"]
    task_id: str | None = None
    pipeline_id: str | None = None
    intent: str | None = None
    missing_params: list[str] | None = None
    pipeline: dict | None = None
    reply_text: str | None = None


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
                result = await agent.run(message, task_id=_tid)
            r = result.to_dict()
            await _emit_skill_result(_tid, {
                "skill": "research",
                "summary_ar": r.get("summary", ""),
                "sources": r.get("sources", []),
                "artifacts_dir": r.get("artifacts_dir"),
            })
            return r
        return task_manager.submit("run", {"goal": message}, _factory).task_id

    if intent_kind == "explore":
        from ...skills.explore import explore as _explore_skill

        async def _explore_factory(_tid: str):
            er = await _explore_skill(url or "", params.get("depth_hint") or "thorough")
            result = {"site": er.site, "report": er.report, "report_path": er.report_path}
            await _emit_skill_result(_tid, {
                "skill": "explore",
                "site": er.site,
                "report": er.report,
                "report_path": er.report_path,
                "summary_ar": er.report.get("executive_summary", "") if isinstance(er.report, dict) else "",
            })
            return result
        return task_manager.submit("explore", {"goal": message, "url": url}, _explore_factory).task_id

    if intent_kind == "clone":
        from ...skills.clone import clone as _clone_skill

        async def _clone_factory(_tid: str):
            cr = await _clone_skill(url or "", max_assets=int(params.get("max_assets") or 60))
            result = {
                "url": cr.url, "raw_dir": cr.raw_dir,
                "rebuilt_html_path": cr.rebuilt_html_path, "assets": cr.assets,
            }
            await _emit_skill_result(_tid, {
                "skill": "clone",
                "url": cr.url,
                "rebuilt_html_path": cr.rebuilt_html_path,
                "assets_count": len(cr.assets),
                "summary_ar": f"تم استنساخ {cr.url} — {len(cr.assets)} ملف",
            })
            return result
        return task_manager.submit("clone", {"goal": message, "url": url}, _clone_factory).task_id

    if intent_kind == "components":
        from ...skills.find_components import find_components as _find_components

        async def _components_factory(_tid: str):
            comp_r = await _find_components(params.get("query") or message,
                                            max_pages=int(params.get("max_pages") or 5))
            result = comp_r.to_dict()
            await _emit_skill_result(_tid, {
                "skill": "components",
                **result,
                "summary_ar": result.get("summary_ar", f"تم العثور على {result.get('total_variants', 0)} مكون"),
            })
            return result
        return task_manager.submit("find_components", {"goal": message}, _components_factory).task_id

    if intent_kind == "design_tokens":
        from ...skills.design_tokens import extract_design_tokens as _dt_skill

        async def _dt_factory(_tid: str):
            dt = await _dt_skill(url or "")
            result = dt.to_dict()
            await _emit_skill_result(_tid, {
                "skill": "design_tokens",
                **result,
                "summary_ar": result.get("summary_ar", f"رموز التصميم لـ {url}"),
            })
            return result
        return task_manager.submit("design_tokens", {"goal": message, "url": url}, _dt_factory).task_id

    if intent_kind == "login":
        from ..main import _dispatch_skill_intent
        from ...core.intent_router import Intent

        rec = _dispatch_skill_intent(
            Intent(kind=intent_kind, goal=message, url=url, params=params, confidence=0.85),
            body=_FakeRunBody(),  # type: ignore[arg-type]
        )
        return rec.task_id

    if intent_kind == "signup":
        from ..main import _dispatch_skill_intent
        from ...core.intent_router import Intent

        rec = _dispatch_skill_intent(
            Intent(kind=intent_kind, goal=message, url=url, params=params, confidence=0.85),
            body=_FakeRunBody(),  # type: ignore[arg-type]
        )
        return rec.task_id

    if intent_kind == "temp_signup":
        from ..main import _dispatch_skill_intent
        from ...core.intent_router import Intent

        rec = _dispatch_skill_intent(
            Intent(kind=intent_kind, goal=message, url=url, params=params, confidence=0.85),
            body=_FakeRunBody(),  # type: ignore[arg-type]
        )
        return rec.task_id

    if intent_kind == "site_clone":
        from ...skills.site_clone import site_clone as _site_clone_skill

        async def _site_clone_factory(_tid: str):
            sc_r = await _site_clone_skill(url or "", max_pages=int(params.get("max_pages") or 50))
            result = sc_r.to_dict()
            await _emit_skill_result(_tid, {
                "skill": "site_clone",
                **result,
                "summary_ar": f"تم نسخ {result.get('total_pages', 0)} صفحة من {url}",
            })
            return result
        return task_manager.submit("site_clone", {"goal": message, "url": url}, _site_clone_factory).task_id

    if intent_kind == "md_writer":
        from ...skills.md_writer import md_writer as _md_writer_skill

        async def _md_writer_factory(_tid: str):
            r = await _md_writer_skill(message)
            result = {"content": r.content, "filename": r.filename, "path": r.path, "word_count": r.word_count}
            await _emit_skill_result(_tid, {
                "skill": "md_writer",
                **result,
                "summary_ar": f"تم كتابة وثيقة Markdown ({r.word_count} كلمة)",
            })
            return result
        return task_manager.submit("md_writer", {"goal": message}, _md_writer_factory).task_id

    if intent_kind == "html_artifact":
        from ...skills.html_artifact import html_artifact as _html_skill

        async def _html_factory(_tid: str):
            r = await _html_skill(message)
            result = {"content": r.content, "filename": r.filename, "path": r.path}
            await _emit_skill_result(_tid, {
                "skill": "html_artifact",
                **result,
                "summary_ar": f"تم إنشاء صفحة HTML: {r.filename}",
            })
            return result
        return task_manager.submit("html_artifact", {"goal": message}, _html_factory).task_id

    if intent_kind == "code_artifact":
        from ...skills.code_artifact import code_artifact as _code_skill

        async def _code_factory(_tid: str):
            r = await _code_skill(message, params.get("language") or "")
            result = {"content": r.content, "language": r.language, "filename": r.filename, "path": r.path}
            await _emit_skill_result(_tid, {
                "skill": "code_artifact",
                **result,
                "summary_ar": f"تم توليد كود {r.language}: {r.filename}",
            })
            return result
        return task_manager.submit("code_artifact", {"goal": message}, _code_factory).task_id

    if intent_kind == "mermaid_diagram":
        from ...skills.mermaid_diagram import mermaid_diagram as _mermaid_skill

        async def _mermaid_factory(_tid: str):
            r = await _mermaid_skill(message)
            result = {"content": r.content, "diagram_type": r.diagram_type, "filename": r.filename, "path": r.path}
            await _emit_skill_result(_tid, {
                "skill": "mermaid_diagram",
                **result,
                "summary_ar": f"تم رسم مخطط {r.diagram_type}",
            })
            return result
        return task_manager.submit("mermaid_diagram", {"goal": message}, _mermaid_factory).task_id

    if intent_kind == "pdf_export":
        # PDF is rendered client-side; backend generates the markdown content
        from ...skills.md_writer import md_writer as _pdf_md_skill

        async def _pdf_factory(_tid: str):
            r = await _pdf_md_skill(message)
            result = {"content": r.content, "filename": r.filename, "path": r.path, "word_count": r.word_count}
            await _emit_skill_result(_tid, {
                "skill": "pdf_export",
                **result,
                "summary_ar": f"المحتوى جاهز للتصدير كـ PDF ({r.word_count} كلمة)",
            })
            return result
        return task_manager.submit("pdf_export", {"goal": message}, _pdf_factory).task_id

    if intent_kind == "summarize":
        from ...skills.summarize import summarize as _summarize_skill

        async def _summarize_factory(_tid: str):
            r = await _summarize_skill(message, goal=message)
            result = {
                "summary_ar": r.summary_ar,
                "bullets": r.bullets,
                "original_word_count": r.original_word_count,
                "summary_word_count": r.summary_word_count,
            }
            await _emit_skill_result(_tid, {
                "skill": "summarize",
                **result,
            })
            return result
        return task_manager.submit("summarize", {"goal": message}, _summarize_factory).task_id

    if intent_kind == "translate":
        from ...skills.translate import translate as _translate_skill

        async def _translate_factory(_tid: str):
            r = await _translate_skill(message, target_lang=params.get("target_lang") or "")
            result = {
                "original": r.original,
                "translated": r.translated,
                "source_lang": r.source_lang,
                "target_lang": r.target_lang,
            }
            await _emit_skill_result(_tid, {
                "skill": "translate",
                **result,
                "summary_ar": f"ترجمة من {r.source_lang} إلى {r.target_lang}",
            })
            return result
        return task_manager.submit("translate", {"goal": message}, _translate_factory).task_id

    if intent_kind == "competitor_matrix":
        from ...skills.competitor_matrix import competitor_matrix as _matrix_skill

        async def _matrix_factory(_tid: str):
            r = await _matrix_skill(message)
            result = {
                "competitors": r.competitors,
                "features": r.features,
                "matrix": r.matrix,
                "csv_content": r.csv_content,
                "filename": r.filename,
                "path": r.path,
            }
            await _emit_skill_result(_tid, {
                "skill": "competitor_matrix",
                **result,
                "summary_ar": f"مصفوفة مقارنة {len(r.competitors)} منافس × {len(r.features)} معيار",
            })
            return result
        return task_manager.submit("competitor_matrix", {"goal": message}, _matrix_factory).task_id

    # Default fallback — research.
    from ...core.agent import Agent as _AgentFallback

    async def _fallback_factory(_tid: str):
        async with _AgentFallback() as agent:
            result = await agent.run(message, task_id=_tid)
        r = result.to_dict()
        await _emit_skill_result(_tid, {
            "skill": "research",
            "summary_ar": r.get("summary", ""),
        })
        return r
    return task_manager.submit("run", {"goal": message}, _fallback_factory).task_id


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

    # ── 1b. Chat branch — greeting / simple conversational message ────────────
    if kind == "chat":
        llm = get_provider(settings)
        system = (
            "أنت مساعد ذكاء اصطناعي ودود ومحترف. تتحدث العربية والإنجليزية بطلاقة. "
            "أجب على التحيات والأسئلة البسيطة بشكل طبيعي وودود وبإيجاز — لا تكن طويلاً. "
            "إذا احتاج المستخدم بحثاً في الإنترنت أو معلومات من مواقع، يمكنه كتابة سؤاله وستبحث له فوراً."
        )
        try:
            reply = await asyncio.wait_for(
                llm.chat([
                    {"role": "system", "content": system},
                    {"role": "user", "content": body.message},
                ]),
                timeout=20.0,
            )
        except Exception:
            reply = "أهلاً وسهلاً! كيف يمكنني مساعدتك اليوم؟"
        return ChatResponse(mode="chat", reply_text=reply)

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
