"""Turn a natural-language goal into an initial plan + define the step schema."""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing import Any

from .prompt_loader import load_prompt


def _system_planner(locale: str = "ar") -> str:
    """Load the planner system prompt for the given locale."""
    return load_prompt("planner", locale=locale)


def _system_decider(locale: str = "ar") -> str:
    """Load the decider (single-turn action picker) system prompt."""
    return load_prompt("decider", locale=locale)


@dataclass
class Plan:
    goal: str
    success_criteria: list[str]
    starting_url: str | None
    subtasks: list[str]

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "success_criteria": self.success_criteria,
            "starting_url": self.starting_url,
            "subtasks": self.subtasks,
        }


class Planner:
    def __init__(self, llm: Any, *, locale: str = "ar") -> None:
        self.llm = llm
        self.locale = locale

    async def plan(self, goal: str, context: str | None = None) -> Plan:
        """Produce a structured plan from a natural-language goal.

        Falls back to a minimal stub plan if the LLM produces invalid
        JSON or chokes on the input (we've seen mistral-small enter a
        repetition loop on certain Arabic prompts and emit a degenerate
        response that's neither valid JSON nor truncated cleanly).
        """
        user = f"GOAL: {goal}"
        if context:
            user += f"\n\nADDITIONAL CONTEXT:\n{context}"
        try:
            data = await self.llm.chat_json(_system_planner(self.locale), user)
            if not isinstance(data, dict):
                raise ValueError(f"planner returned non-dict: {type(data).__name__}")
        except Exception as exc:  # noqa: BLE001
            # Don't kill the task on planner failure — emit a usable stub
            # and let the decide-loop figure out the details. The decider
            # has its own JSON-recovery retry and sees the raw goal, so
            # it can still drive a sensible run.
            from ..utils.logger import log
            log.warning(
                f"Planner LLM call failed ({type(exc).__name__}: {exc!s:.150}). "
                "Falling back to stub plan."
            )
            return Plan(
                goal=goal,
                success_criteria=[
                    "User goal is answered with concrete information",
                    "At least one extraction from a relevant page",
                ],
                starting_url=None,
                subtasks=[
                    "search_web for the goal in its original language",
                    "Pick the most relevant result and goto it",
                    "extract the content",
                    "emit done with a summary of the findings",
                ],
            )
        return Plan(
            goal=data.get("goal") or goal,
            success_criteria=list(data.get("success_criteria") or []),
            starting_url=data.get("starting_url"),
            subtasks=list(data.get("subtasks") or []),
        )

    async def decide(
        self,
        goal: str,
        history: list[dict],
        snapshot_text: str,
        screenshot_bytes: bytes | None = None,
        use_vision: bool = False,
        *,
        subtasks: list[str] | None = None,
        context: str | None = None,
    ) -> dict:
        # The decider previously saw only the GOAL, not the planner's
        # subtasks. That meant a careful plan ("search_web for موقع ديل
        # للعقارات") could be totally ignored at execution time because
        # the LLM-decider re-derived everything from the bare goal.
        # We now surface BOTH the subtasks and the memory/archive
        # disambiguation context so the decider follows the plan AND
        # remembers what 'ديل' meant last time.
        history_text = json.dumps(history[-12:], ensure_ascii=False, indent=2)
        parts = [f"GOAL:\n{goal}"]
        if subtasks:
            steps = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(subtasks))
            parts.append(f"PLAN SUBTASKS (follow these — they are the playbook):\n{steps}")
        if context:
            parts.append(f"PRIOR-RUN CONTEXT (use to disambiguate the goal):\n{context}")
        parts.append(f"ACTION HISTORY (most recent last):\n{history_text}")
        parts.append(f"CURRENT PAGE SNAPSHOT:\n{snapshot_text}")
        parts.append("Respond with a single JSON action.")
        user = "\n\n".join(parts)

        system = _system_decider(self.locale)
        if use_vision and screenshot_bytes:
            return await self.llm.vision_json(
                prompt=system + "\n\n" + user,
                image_bytes=screenshot_bytes,
            )
        return await self.llm.chat_json(system, user)
