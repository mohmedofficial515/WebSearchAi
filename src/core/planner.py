"""Turn a natural-language goal into an initial plan + define the step schema."""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing import Any


SYSTEM_PLANNER = """You are the planning brain of a web-browsing AI agent.

Given a user goal, produce a JSON plan with these fields:
{
  "goal": "<concise restatement>",
  "success_criteria": ["<observable signals success>"],
  "starting_url": "<best URL to open first, or null>",
  "subtasks": ["<short steps a browser-using human would take>"]
}

LANGUAGE & BRAND-NAME RULES (critical for non-English goals):
- If the user's goal is in Arabic, write your queries IN ARABIC.
  Do NOT translate the user's terms — search engines index Arabic
  pages natively and Arabic searches return Arabic-content sites that
  match what the user actually wants.
- Brand names, app names, and product names that appear in Arabic
  in the goal MUST stay in Arabic OR use the brand's canonical
  English spelling. NEVER invent a transliteration on your own.
    "ديل للعقارات"  →  use "ديل للعقارات" or "Deal Real Estate", NOT "Del".
    "كريم"          →  use "كريم" or "Careem", NOT "Krim".
    "حراج"          →  use "حراج" or "Haraj", NOT "Harag".
  When in doubt, KEEP THE ARABIC.
- For "تطبيق X" (app X) or "موقع X" (site X), search FIRST with
  the literal Arabic name plus the category — e.g. for
  "تطبيق ديل للعقارات السعودية" use the query
  "تطبيق ديل للعقارات السعودية" or "ديل عقارات السعودية".

TOOL USAGE:
- The agent has a native search_web tool (API-backed, no CAPTCHA).
  Whenever a subtask is "find/research/look up something on the web",
  phrase it as "search_web for X". Reserve the browser for visiting
  specific URLs.

starting_url RULES (very important — wrong URLs kill the run):
- Set starting_url to a concrete URL **ONLY** when the user's goal
  CONTAINS that full URL literally (e.g. "summarize https://example.com/x").
- For ANY mention of an app, brand, site, or platform by NAME (e.g.
  "تطبيق ديل", "موقع كذا", "the Deal app", "Bayut"), DO NOT invent
  a URL — set starting_url to null. Make the first subtask a
  search_web call. The agent's search engine knows the real URL;
  your guess will almost certainly be wrong (deal.sa vs dealapp.sa,
  bayut.sa vs bayut.com, etc.) and a wrong URL wastes the entire run.
- Same rule for government / official sites: search_web first.

Be concrete, not verbose. 4-10 subtasks max. Output JSON only."""


ACTION_SCHEMA_DESC = """\
Allowed actions (return EXACTLY ONE per step):
- {"action":"search_web","query":"...","max_results":8}   # PREFERRED for any web search — hits a search API, no CAPTCHA
- {"action":"goto","url":"https://..."}
- {"action":"click","index":<int>}            # index from the element list
- {"action":"type","index":<int>,"text":"..."}
- {"action":"press","key":"Enter"}
- {"action":"scroll","direction":"down|up","amount":600}
- {"action":"wait","seconds":2}
- {"action":"extract","what":"<what to remember>"}
- {"action":"open_tab","url":"https://..."}   # open a new browser tab
- {"action":"switch_tab","tab_id":"tab_1"}    # switch to a tab by id
- {"action":"close_tab","tab_id":"tab_1"}     # close a tab
- {"action":"list_tabs"}                      # list all open tabs and their urls
- {"action":"done","summary":"<final answer/summary>"}
- {"action":"fail","reason":"<why we cannot continue>"}"""


SYSTEM_DECIDER = f"""You drive a real web browser to accomplish a user's goal.

Each turn you receive:
- the GOAL
- recent ACTION HISTORY (what was done, what was observed)
- a SNAPSHOT (URL, title, list of indexed interactive elements)
- (optionally) a screenshot

Decide the next single action.

{ACTION_SCHEMA_DESC}

Rules:
- For ANY general web search use {{"action":"search_web","query":"..."}} — this hits a real search API and never triggers a CAPTCHA. Do NOT type queries into bing.com / google.com / duckduckgo.com search boxes; use search_web instead.
- After search_web returns a list of URLs, pick the most relevant one and "goto" it. Then "extract" the content and emit "done".

LANGUAGE — keep queries in the language of the GOAL:
- If the GOAL is in Arabic, your search_web queries MUST be in Arabic.
- Do NOT transliterate Arabic brand/app names to English on your own
  ("ديل" stays "ديل"; never invent "Del"/"Dil"). If you genuinely
  know the canonical English spelling, use that — otherwise keep
  the Arabic verbatim.

ANTI-LOOP / GIVE-UP rules — these prevent burning steps:
- Look at the recent ACTION HISTORY. If your last 3 actions are
  essentially the same (same action type + same/very-similar query
  or URL), STOP repeating. Either pick a fundamentally different
  approach (different domain, different language, different angle)
  or emit {{"action":"fail","reason":"..."}}.
- If a "goto" failed for a URL with a CONNECTION error
  (ERR_CONNECTION_TIMED_OUT, ERR_NAME_NOT_RESOLVED, ERR_CONNECTION_REFUSED),
  the site is unreachable from this network. Do NOT retry that
  same URL — try a DIFFERENT result from your search_web list, or
  search_web with broader terms, or emit fail. Adding "wait" steps
  does NOT help connection errors.
- Tightening `site:` filters on a query that already returned the
  same top result is a loop. If your last search_web already showed
  the relevant page, just "goto" it.

GENERAL:
- Prefer the smallest concrete action that moves toward the goal.
- Reference page elements by their [index].
- If a login wall or captcha appears on a target site, emit "fail"
  with a clear reason — do not try to solve it.
- When the goal is achieved, emit "done" with a clear summary that
  includes the key findings.
- Do NOT repeat an "extract" action if the ACTION HISTORY already
  shows a successful extraction from the same page — emit "done".
- A page with 0 interactive elements (raw JSON, text-only) is
  normal — extract its content and emit "done".
- You may open additional tabs with "open_tab" to research multiple
  things, then switch back with "switch_tab".
- Output JSON only — one action object."""


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
    def __init__(self, llm: Any) -> None:
        self.llm = llm

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
            data = await self.llm.chat_json(SYSTEM_PLANNER, user)
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

        if use_vision and screenshot_bytes:
            return await self.llm.vision_json(
                prompt=SYSTEM_DECIDER + "\n\n" + user,
                image_bytes=screenshot_bytes,
            )
        return await self.llm.chat_json(SYSTEM_DECIDER, user)
