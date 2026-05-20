"""Memory recall + archive persistence helpers for `Agent`.

These functions reference only data that flows through the agent's
main loop (the goal string, the final plan, the step history, the
verdict). They do **not** touch the live browser session, so factoring
them out of `Agent` keeps the class focused on the perceive-decide-act
loop and shrinks `agent.py` significantly.

All three functions are best-effort: any failure is logged and
swallowed so they cannot fail an otherwise successful task.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from ..config import settings
from ..utils.logger import log
from .planner import Plan


async def get_memory_context(goal: str) -> str | None:
    """Build a planner-context hint from prior successful runs.

    Two sources are consulted, and any that fire are concatenated:
      (1) Site-flow memory — a previously successful flow on a
          domain mentioned literally in the goal.
      (2) Task archive — a paraphrase of this goal we've already
          answered. Used at a *lower* threshold than the auto-cache
          short-circuit, because here we're not replacing the run,
          we're just disambiguating it. e.g. user types "تطبيق ديل"
          today; a week ago they ran "تطبيق ديل العقاري" — we surface
          "ديل ⇒ dealapp.sa real estate" so the LLM doesn't drift
          to dell.com.
    """
    parts: list[str] = []

    # (1) site-flow memory ----------------------------------------------------
    try:
        from ..memory import get_memory

        m = re.search(r"https?://[^\s]+", goal)
        if m:
            domain_url = f"https://{urlparse(m.group(0)).netloc}"
            if urlparse(domain_url).netloc:
                mem = await get_memory()
                cached = await mem.recall_flow(domain_url, "browse")
                if cached:
                    parts.append(
                        f"Previously successful flow for "
                        f"{urlparse(domain_url).netloc} "
                        f"({cached.get('success_count', 1)} run(s)):\n"
                        + json.dumps(cached["flow_data"], ensure_ascii=False)
                    )
    except Exception as exc:  # noqa: BLE001 — memory layer is wide; never block a real run
        log.debug(f"Memory context (site-flow) skipped: {exc}")

    # (2) archive paraphrase hint --------------------------------------------
    # Skipped when research_fresh_runs is on — the user explicitly
    # asked never to bias new runs on cached answers. Site-flow
    # memory (above) still applies because that's login plumbing,
    # not goal-answer reuse.
    if getattr(settings, "research_fresh_runs", True):
        return "\n\n".join(parts) if parts else None
    try:
        from ..archive import get_archive
        arc = await get_archive()
        # Threshold here is below the auto-cache threshold but
        # above noise. 0.35–0.85 means "you've answered something
        # related — use it to ground the new run."
        hit = await arc.find_similar(goal, threshold=0.35)
        if hit and hit.score < 0.85:  # 0.85+ is handled by /api/run cache
            rec = hit.record
            # Pull a short snippet of the prior summary to anchor
            # the model. Hard-cap to keep the planner prompt tight.
            summary = rec.summary
            if isinstance(summary, dict):
                summary = json.dumps(summary, ensure_ascii=False)[:300]
            summary = str(summary or "")[:300]
            starting_url = rec.starting_url or ""
            terms = ", ".join(hit.matched_terms[:6]) or "(none)"
            parts.append(
                "PRIOR-RUN HINT (use to disambiguate, do NOT copy "
                "the answer — the user may want fresh info):\n"
                f"  past goal: {rec.goal!r}\n"
                f"  similarity: {hit.score:.2f} (shared terms: {terms})\n"
                f"  past answer was about: {summary}\n"
                + (f"  past starting URL that worked: {starting_url}\n"
                   if starting_url else "")
                + "If the current goal is asking about the SAME entity "
                "(same app/site/topic), trust the past starting URL "
                "instead of guessing a new one."
            )
    except Exception as exc:  # noqa: BLE001 — archive layer is wide; never block a real run
        log.debug(f"Memory context (archive) skipped: {exc}")

    return "\n\n".join(parts) if parts else None


async def archive_task(
    *,
    task_id: str,
    goal: str,
    plan: Plan,
    history: list[dict],
    extractions: list[str],
    final_summary: str,
    verdict: dict,
) -> None:
    """Persist a successful task to the durable archive so a future
    identical/similar request can short-circuit to the cached answer."""
    try:
        from ..archive import get_archive

        archive = await get_archive()
        result_payload = {
            "task_id": task_id,
            "goal": goal,
            "success": True,
            "confidence": float(verdict.get("confidence") or 0.0),
            "summary": final_summary,
            "reason": str(verdict.get("reason") or ""),
            "plan": plan.to_dict(),
            "steps": history,
            "extractions": extractions,
        }
        await archive.save(task_id, goal, result_payload)
        log.info(f"📚 Archived task {task_id}: {goal[:60]!r}")
    except Exception as exc:  # noqa: BLE001 — archive save is best-effort; do not fail the task
        log.debug(f"Archive save skipped: {exc}")


async def save_memory(
    plan: Plan, history: list[dict], extractions: list[str]
) -> None:
    """Touch the site in long-term memory and remember the successful flow."""
    try:
        from ..memory import get_memory

        mem = await get_memory()
        await mem.touch_site(plan.starting_url)  # type: ignore[arg-type]
        flow = {
            "subtasks": plan.subtasks,
            "step_count": len(history),
            "extractions": extractions[:3],
        }
        await mem.remember_flow(plan.starting_url, "browse", flow)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — memory save is best-effort
        log.debug(f"Memory save skipped: {exc}")


__all__ = ["get_memory_context", "archive_task", "save_memory"]
