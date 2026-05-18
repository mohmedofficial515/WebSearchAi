"""Skill: generate code in any programming language."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class CodeArtifactResult:
    content: str
    language: str
    filename: str
    path: str


_LANG_EXT: dict[str, str] = {
    "python": "py",
    "typescript": "ts",
    "javascript": "js",
    "html": "html",
    "css": "css",
    "json": "json",
    "sql": "sql",
    "bash": "sh",
    "shell": "sh",
    "rust": "rs",
    "go": "go",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "cs",
    "yaml": "yaml",
    "toml": "toml",
}

_SYSTEM = (
    "أنت مبرمج خبير. اكتب كوداً نظيفاً واحترافياً بناءً على طلب المستخدم.\n"
    "أرجع JSON فقط بالشكل التالي:\n"
    "{\"language\": \"python\", \"code\": \"...\"}\n"
    "اختر اللغة الأنسب إذا لم تُحدد. الكود يجب أن يكون قابلاً للتشغيل مباشرةً."
)


async def code_artifact(goal: str, language: str = "") -> CodeArtifactResult:
    llm = get_provider(settings)
    try:
        log.info("code_artifact: generating for goal=%r lang=%r", goal[:80], language)
        user_msg = goal if not language else f"اللغة المطلوبة: {language}\n\n{goal}"
        data = await llm.chat_json(_SYSTEM, user_msg)
    finally:
        await llm.close()

    detected_lang = str(data.get("language", language or "python")).lower()
    code = str(data.get("code", ""))

    ext = _LANG_EXT.get(detected_lang, detected_lang[:4] or "txt")
    out_dir = Path(settings.output_path) / "artifacts" / "code"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", goal[:40]).strip("_")
    filename = f"{safe}_{int(time.time())}.{ext}"
    path = out_dir / filename
    path.write_text(code, encoding="utf-8")

    return CodeArtifactResult(content=code, language=detected_lang, filename=filename, path=str(path))
