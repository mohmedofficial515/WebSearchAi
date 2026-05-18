"""Skill: generate a complete HTML page artifact."""
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


_SYSTEM = (
    "أنت مطور ويب خبير. أنتج صفحة HTML كاملة واحترافية بناءً على طلب المستخدم.\n"
    "الصفحة يجب أن تتضمن:\n"
    "  - DOCTYPE html، meta charset UTF-8، meta viewport\n"
    "  - تصميم جميل باستخدام CSS inline أو داخل <style>\n"
    "  - دعم RTL إذا كان المحتوى عربياً\n"
    "  - لا تعتمد على مكتبات خارجية — كل شيء self-contained\n"
    "أرجع كود HTML فقط — ابدأ بـ <!DOCTYPE html> مباشرةً."
)


async def html_artifact(goal: str) -> HtmlArtifactResult:
    llm = get_provider(settings)
    try:
        log.info("html_artifact: generating for goal=%r", goal[:80])
        content = await llm.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": goal},
            ],
            max_tokens=6000,
            temperature=0.3,
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
