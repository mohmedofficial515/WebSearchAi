"""Skill: generate a Mermaid diagram from a user description."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class MermaidDiagramResult:
    content: str
    diagram_type: str
    filename: str
    path: str


_SYSTEM = (
    "أنت خبير في رسم المخططات باستخدام Mermaid.\n"
    "أرجع JSON فقط بالشكل:\n"
    "{\"diagram_type\": \"flowchart\", \"code\": \"flowchart TD\\n  A-->B\"}\n"
    "اختر النوع المناسب (flowchart, sequenceDiagram, classDiagram, stateDiagram-v2, "
    "gantt, pie, erDiagram, journey).\n"
    "تأكد أن الكود صحيح وقابل للعرض. استخدم label عربي إذا كان الطلب عربياً."
)


async def mermaid_diagram(goal: str) -> MermaidDiagramResult:
    llm = get_provider(settings)
    try:
        log.info("mermaid_diagram: generating for goal=%r", goal[:80])
        data = await llm.chat_json(_SYSTEM, goal)
    finally:
        await llm.close()

    diagram_type = str(data.get("diagram_type", "flowchart"))
    content = str(data.get("code", ""))

    # Strip accidental code fences
    content = re.sub(r"^```mermaid\s*\n?", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\n?```\s*$", "", content.strip())

    out_dir = Path(settings.output_path) / "artifacts" / "mermaid"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", goal[:40]).strip("_")
    filename = f"{safe}_{int(time.time())}.mmd"
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")

    return MermaidDiagramResult(content=content, diagram_type=diagram_type, filename=filename, path=str(path))
