"""Skill: explore a site like a human and produce a feature/UX report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..core.agent import Agent
from ..llm.providers import get_provider


REPORT_SYSTEM = """You are a senior product analyst.

You will receive a transcript of a browser-using AI agent that explored a website.
Produce a JSON report:
{
  "site": "...",
  "purpose": "...",                       # what the site does
  "main_features": ["..."],               # 5-15 user-visible features
  "key_user_flows": ["..."],              # signup, checkout, etc.
  "tech_signals": ["..."],                # framework hints, third-party scripts
  "design_notes": {"palette":[..],"typography":"...","layout":"..."},
  "clone_recipe": ["short ordered steps to rebuild a similar site"],
  "risks_or_blockers": ["..."]
}
"""


@dataclass
class ExploreReport:
    site: str
    report: dict
    report_path: str


async def explore(site_url: str, depth_hint: str = "thorough") -> ExploreReport:
    goal = (
        f"Visit {site_url} and explore it like a curious power-user.\n"
        "Walk through the home page, the main navigation, sign-up/login pages, "
        "pricing/product pages, footer links. For each page, extract a short "
        "description of the visible features. Do NOT submit any forms or create "
        "real accounts. End with a 'done' action whose summary lists all features "
        f"you discovered. Depth: {depth_hint}."
    )

    async with Agent() as agent:
        result = await agent.run(goal)

    transcript = json.dumps(
        {
            "goal": goal,
            "plan": result.plan,
            "steps": result.steps,
            "summary": result.summary,
            "extractions": result.extractions[-10:],
        },
        ensure_ascii=False,
        indent=2,
    )

    llm = get_provider(settings)
    try:
        report = await llm.chat_json(REPORT_SYSTEM, transcript)
    finally:
        await llm.close()

    out_dir = Path(settings.output_path) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = site_url.replace("https://", "").replace("http://", "").replace("/", "_")[:80]
    path = out_dir / f"{safe}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return ExploreReport(site=site_url, report=report, report_path=str(path))
