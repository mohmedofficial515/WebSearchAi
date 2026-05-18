"""Skill: generate a competitive analysis matrix for given competitors/products."""
from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from ..llm.providers import get_provider
from ..utils.logger import log


@dataclass
class CompetitorMatrixResult:
    competitors: list[str]
    features: list[str]
    matrix: list[dict[str, Any]]  # [{competitor, feature1, feature2, ...}]
    csv_content: str
    filename: str
    path: str


_SYSTEM = (
    "أنت محلل أعمال خبير. أنشئ مصفوفة مقارنة احترافية للمنافسين أو المنتجات.\n"
    "أرجع JSON فقط بالشكل:\n"
    "{\n"
    "  \"competitors\": [\"شركة أ\", \"شركة ب\", \"شركة ج\"],\n"
    "  \"features\": [\"السعر\", \"الميزات\", \"سهولة الاستخدام\", \"الدعم\"],\n"
    "  \"matrix\": [\n"
    "    {\"competitor\": \"شركة أ\", \"السعر\": \"مجاني\", \"الميزات\": \"محدودة\", ...},\n"
    "    ...\n"
    "  ]\n"
    "}\n"
    "يجب أن تشمل المصفوفة 3-6 منافسين و4-8 معايير مقارنة واقعية وموضوعية.\n"
    "اكتب القيم بشكل مختصر وواضح (كلمة أو عبارة قصيرة لكل خلية)."
)


def _build_csv(matrix: list[dict[str, Any]], features: list[str]) -> str:
    buf = io.StringIO()
    cols = ["competitor"] + features
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in matrix:
        writer.writerow(row)
    return buf.getvalue()


async def competitor_matrix(goal: str) -> CompetitorMatrixResult:
    llm = get_provider(settings)
    try:
        log.info("competitor_matrix: generating for goal=%r", goal[:80])
        data = await llm.chat_json(_SYSTEM, goal)
    finally:
        await llm.close()

    competitors: list[str] = [str(c) for c in data.get("competitors", [])]
    features: list[str] = [str(f) for f in data.get("features", [])]
    matrix: list[dict[str, Any]] = data.get("matrix", [])

    csv_content = _build_csv(matrix, features)

    out_dir = Path(settings.output_path) / "artifacts" / "competitor"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", goal[:40]).strip("_")
    filename = f"{safe}_{int(time.time())}.csv"
    path = out_dir / filename
    path.write_text(csv_content, encoding="utf-8")

    return CompetitorMatrixResult(
        competitors=competitors,
        features=features,
        matrix=matrix,
        csv_content=csv_content,
        filename=filename,
        path=str(path),
    )
