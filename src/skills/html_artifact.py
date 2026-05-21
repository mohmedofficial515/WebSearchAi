"""Skill: generate a complete, professional HTML page artifact."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class HtmlArtifactResult:
    content: str
    filename: str
    path: str


_SYSTEM = """\
أنت مصمم ويب خبير ومطور front-end محترف. مهمتك إنشاء صفحات HTML كاملة واحترافية \
ذات جودة إنتاجية عالية بناءً على وصف المستخدم.

قواعد الإنتاج:
1. ابدأ دائماً بـ <!DOCTYPE html> — لا شيء قبلها.
2. استخدم meta charset="UTF-8" و meta viewport.
3. الخطوط: استخدم Google Fonts عبر CDN (رابط <link> في <head>).
   - للمحتوى العربي: اختر من (Tajawal, Cairo, Almarai, IBM Plex Arabic, Rubik).
   - للمحتوى الإنجليزي: اختر من (Inter, Poppins, Nunito, Raleway, Montserrat).
4. الأيقونات: استخدم Font Awesome 6 عبر CDN:
   <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
5. CSS: كل الأنماط داخل <style> في <head> — لا ملفات خارجية.
   استخدم CSS Variables لـ (--primary-color, --secondary-color, --font-main, --bg-color).
   استخدم Flexbox/Grid للتخطيط. أضف :hover transitions ناعمة.
6. RTL: إذا كان المحتوى عربياً، أضف dir="rtl" على <html> و text-align: right على body.
7. الصور: استخدم Unsplash (https://source.unsplash.com/800x400/?keyword) أو SVG placeholders.
8. الكود يجب أن يكون self-contained تماماً — لا JS imports خارجية.
9. الجودة البصرية: تدرجات ألوان (gradients)، ظلال (box-shadow)، زوايا مدوّرة، تباعد سخي.
10. أرجع HTML نقياً فقط — ابدأ بـ <!DOCTYPE html> مباشرةً، لا شرح ولا markdown.
"""


async def html_artifact(goal: str, *, context: str = "") -> HtmlArtifactResult:
    llm = get_provider(settings)
    if context:
        user_prompt = f"{context}\n\nالمهمة الحالية:\n{goal}"
    else:
        user_prompt = goal

    try:
        log.info("html_artifact: generating for goal=%r", goal[:80])
        content = await llm.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=8000,
            temperature=0.25,
        )
    finally:
        await llm.close()

    # Strip markdown code fences if the LLM wrapped the output
    content = re.sub(r"^```html?\s*\n?", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\n?```\s*$", "", content.strip())

    out_dir = Path(settings.output_path) / "artifacts" / "html"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", goal[:40]).strip("_")
    filename = f"{safe}_{int(time.time())}.html"
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")

    return HtmlArtifactResult(content=content, filename=filename, path=str(path))
