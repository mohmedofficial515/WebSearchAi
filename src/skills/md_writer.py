"""Skill: write a Markdown document from a user goal."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class MdWriterResult:
    content: str
    filename: str
    path: str
    word_count: int


_SYSTEM = (
    "أنت كاتب محترف متخصص في كتابة التقارير والوثائق بتنسيق Markdown.\n"
    "اكتب وثيقة Markdown احترافية بناءً على طلب المستخدم.\n"
    "استخدم العناوين (##, ###)، والقوائم، والجداول، والتأكيد (**bold**) حيثما يناسب.\n"
    "اكتب بالعربية إلا إذا طُلب غير ذلك صراحةً.\n"
    "أرجع نص Markdown فقط — بدون تفسيرات أو مقدمات."
)


async def md_writer(goal: str) -> MdWriterResult:
    llm = get_provider(settings)
    try:
        log.info("md_writer: generating for goal=%r", goal[:80])
        content = await llm.chat(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": goal},
            ],
            max_tokens=4000,
            temperature=0.3,
        )
    finally:
        await llm.close()

    out_dir = Path(settings.output_path) / "artifacts" / "markdown"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", goal[:40]).strip("_")
    filename = f"{safe}_{int(time.time())}.md"
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")

    word_count = len(content.split())
    return MdWriterResult(content=content, filename=filename, path=str(path), word_count=word_count)
