"""Verify whether the success criteria are satisfied at the end of a run."""

from __future__ import annotations

from typing import Any

from .prompt_loader import load_prompt


def _system_verifier(locale: str = "ar") -> str:
    return load_prompt("verifier", locale=locale)


class Verifier:
    def __init__(self, llm: Any, *, locale: str = "ar") -> None:
        self.llm = llm
        self.locale = locale

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
        return await self.llm.chat_json(_system_verifier(self.locale), user)
