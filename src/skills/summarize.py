"""Skill: summarize text in Arabic with bullet points and word-count delta."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class SummarizeResult:
    summary_ar: str
    bullets: list[str] = field(default_factory=list)
    original_word_count: int = 0
    summary_word_count: int = 0


_SYSTEM = (
    "أنت متخصص في التلخيص الاحترافي. لخّص النص المعطى باللغة العربية.\n"
    "أرجع JSON فقط بالشكل:\n"
    "{\n"
    "  \"summary_ar\": \"ملخص النص هنا\",\n"
    "  \"bullets\": [\"نقطة 1\", \"نقطة 2\", \"نقطة 3\"]\n"
    "}\n"
    "الملخص يجب أن يكون مختصراً ويحتوي على أهم النقاط. "
    "القائمة bullets تحتوي 3-7 نقاط رئيسية."
)


async def summarize(text: str, goal: str = "") -> SummarizeResult:
    llm = get_provider(settings)
    user_content = text if not goal else f"الطلب: {goal}\n\nالنص:\n{text}"
    original_words = len(text.split())

    try:
        log.info("summarize: text_len=%d goal=%r", len(text), goal[:60])
        data = await llm.chat_json(_SYSTEM, user_content)
    finally:
        await llm.close()

    summary_ar = str(data.get("summary_ar", ""))
    bullets = [str(b) for b in data.get("bullets", []) if b]

    return SummarizeResult(
        summary_ar=summary_ar,
        bullets=bullets,
        original_word_count=original_words,
        summary_word_count=len(summary_ar.split()),
    )
