"""Verify whether the success criteria are satisfied at the end of a run."""

from __future__ import annotations

from typing import Any


SYSTEM_VERIFIER = """You are the verifier of a browser-using AI agent.

Given:
- the original GOAL
- the SUCCESS CRITERIA the planner committed to
- the agent's FINAL SUMMARY
- EXTRACTED DATA collected during the run (treat this as primary evidence)
- the FINAL PAGE SNAPSHOT (URL, title, visible elements — may be empty for raw JSON pages)

Rules:
- EXTRACTED DATA is the most important signal. If it contains the requested information, mark success=true.
- The final page snapshot may be empty or minimal (e.g. a raw JSON page) — this is NOT a failure signal.
- Only mark success=false if the goal was clearly NOT achieved.

Return JSON: {"success": true|false, "confidence": 0-1, "reason": "...", "missing": [..]}
"""


class Verifier:
    def __init__(self, llm: Any) -> None:
        self.llm = llm

    async def verify(
        self,
        goal: str,
        success_criteria: list[str],
        final_summary: str,
        final_snapshot_text: str,
        extractions: list[str] | None = None,
    ) -> dict:
        extractions_text = "\n---\n".join((extractions or [])[:3])[:3000] or "(none)"
        user = (
            f"GOAL:\n{goal}\n\n"
            f"SUCCESS CRITERIA:\n- " + "\n- ".join(success_criteria or ["(none)"]) + "\n\n"
            f"EXTRACTED DATA:\n{extractions_text}\n\n"
            f"AGENT FINAL SUMMARY:\n{final_summary}\n\n"
            f"FINAL PAGE SNAPSHOT:\n{final_snapshot_text}\n"
        )
        return await self.llm.chat_json(SYSTEM_VERIFIER, user)
