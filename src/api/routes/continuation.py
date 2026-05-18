"""GET /api/continuation/{task_or_pipeline_id} — completion follow-ups.

After a task/pipeline ends, the ContinuationCard offers 3 suggested
next-step prompts. We pre-compute them asynchronously with a 2-second
timeout: if the LLM is slow we return an empty list and the card simply
shows without suggestions (G18 fix).
"""

from __future__ import annotations

import asyncio
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


# Fallback suggestions per skill kind (used when LLM is unavailable or slow).
_SKILL_DEFAULTS: dict[str, list[tuple[str, str]]] = {
    "research": [
        ("🔍 بحث أعمق", "ابحث بتفصيل أكثر عن {goal}"),
        ("📄 اكتب تقريراً", "اكتب تقرير ماركداون شامل عن {goal}"),
        ("📊 قارن المنافسين", "قارن المنافسين الرئيسيين في مجال {goal}"),
    ],
    "explore": [
        ("🔍 تحليل أعمق", "حلّل {goal} بشكل أعمق"),
        ("📄 تقرير ماركداون", "اكتب تقريراً كاملاً عن تحليل {goal}"),
        ("🏗️ استخرج مكونات الواجهة", "استخرج مكونات الواجهة من {goal}"),
    ],
    "md_writer": [
        ("✏️ تحرير التقرير", "عدّل التقرير الذي كتبته عن {goal}"),
        ("📊 أضف مخططاً", "أضف مخطط Mermaid للتقرير عن {goal}"),
        ("🌐 حوّل إلى HTML", "حوّل التقرير عن {goal} إلى صفحة HTML"),
    ],
    "login": [
        ("📧 تسجيل حساب جديد", "سجّل حساباً جديداً في {goal}"),
        ("🔍 تصفّح الموقع", "تصفّح محتوى {goal} بعد تسجيل الدخول"),
        ("💾 احفظ بيانات الجلسة", "احفظ جلسة تسجيل الدخول في {goal}"),
    ],
    "competitor_matrix": [
        ("📊 تحليل أعمق", "حلّل {goal} بشكل أعمق"),
        ("📄 تقرير ماركداون", "اكتب تقرير ماركداون عن نتائج مقارنة {goal}"),
        ("🔍 ابحث عن منافس جديد", "ابحث عن منافسين جدد في مجال {goal}"),
    ],
    "translate": [
        ("✏️ ترجمة معكوسة", "ترجم مرة أخرى من العربية إلى الإنجليزية: {goal}"),
        ("📄 تقرير عن الترجمة", "اكتب تقريراً عن الفروق الثقافية في ترجمة {goal}"),
        ("🔍 ابحث عن السياق", "ابحث عن السياق الثقافي والمصطلحات في {goal}"),
    ],
    "summarize": [
        ("📄 ملخص أطول", "اكتب ملخصاً أكثر تفصيلاً عن {goal}"),
        ("🌐 ترجم الملخص", "ترجم ملخص {goal} إلى الإنجليزية"),
        ("📊 استخرج النقاط الرئيسية", "استخرج النقاط الرئيسية من {goal}"),
    ],
    "pipeline": [
        ("🔄 تشغيل مهمة مشابهة", "أعد تشغيل {goal}"),
        ("📄 وثّق النتائج", "اكتب تقريراً بنتائج {goal}"),
        ("🔍 تحليل إضافي", "حلّل النتائج بشكل أعمق لـ {goal}"),
    ],
}

_DEFAULT_SUGGESTIONS: list[tuple[str, str]] = [
    ("🔄 مهمة مشابهة", "أعد تنفيذ {goal}"),
    ("📄 اكتب تقريراً", "اكتب تقريراً عن {goal}"),
    ("🔍 ابحث عن المزيد", "ابحث عن مزيد من المعلومات حول {goal}"),
]


def _fallback_suggestions(goal: str, skill: str) -> list[Suggestion]:
    """Return 3 context-appropriate suggestions without calling an LLM."""
    raw = _SKILL_DEFAULTS.get(skill, _DEFAULT_SUGGESTIONS)
    # Trim goal to keep suggestion labels short
    short_goal = goal[:40] + "…" if len(goal) > 40 else goal
    return [
        Suggestion(label_ar=label, prompt=prompt.format(goal=short_goal))
        for label, prompt in raw[:3]
    ]


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

    # Try LLM for richer, context-aware suggestions (2 s budget).
    # On any failure fall back to deterministic skill-based defaults so
    # ContinuationCard never shows an empty suggestion list.
    system = load_prompt("continuation", locale=locale)
    user = (
        f"GOAL: {goal}\n\nSUMMARY:\n{summary or '(empty)'}\n\nSKILL: {skill}"
    )

    llm = None
    try:
        llm = get_provider(settings)
        data: Any = await asyncio.wait_for(llm.chat_json(system, user), timeout=2.0)
        raw = data.get("suggestions") if isinstance(data, dict) else None
        if isinstance(raw, list):
            cleaned: list[Suggestion] = []
            for s in raw[:5]:
                if not isinstance(s, dict):
                    continue
                label = str(s.get("label_ar") or "").strip()
                prompt_text = str(s.get("prompt") or "").strip()
                if label and prompt_text:
                    cleaned.append(Suggestion(label_ar=label, prompt=prompt_text))
            if cleaned:
                return ContinuationResponse(suggestions=cleaned[:3])
    except Exception:
        pass
    finally:
        if llm is not None:
            try:
                await llm.close()
            except Exception:
                pass

    # Deterministic fallback — always returns useful suggestions.
    return ContinuationResponse(suggestions=_fallback_suggestions(goal, skill))
