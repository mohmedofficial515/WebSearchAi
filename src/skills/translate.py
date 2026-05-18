"""Skill: translate text between languages."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class TranslateResult:
    original: str
    translated: str
    source_lang: str
    target_lang: str


_SYSTEM = (
    "أنت مترجم محترف متعدد اللغات.\n"
    "أرجع JSON فقط بالشكل:\n"
    "{\n"
    "  \"source_lang\": \"ar\",\n"
    "  \"target_lang\": \"en\",\n"
    "  \"translated\": \"الترجمة هنا\"\n"
    "}\n"
    "حدد لغة المصدر تلقائياً. الهدف الافتراضي: الإنجليزية إذا كان المصدر عربياً، والعربية للغيرها.\n"
    "الترجمة يجب أن تكون طبيعية وسلسة."
)


async def translate(text: str, target_lang: str = "") -> TranslateResult:
    llm = get_provider(settings)
    user_content = text if not target_lang else f"ترجم إلى: {target_lang}\n\nالنص:\n{text}"

    try:
        log.info("translate: text_len=%d target=%r", len(text), target_lang)
        data = await llm.chat_json(_SYSTEM, user_content)
    finally:
        await llm.close()

    return TranslateResult(
        original=text,
        translated=str(data.get("translated", "")),
        source_lang=str(data.get("source_lang", "auto")),
        target_lang=str(data.get("target_lang", target_lang or "en")),
    )
