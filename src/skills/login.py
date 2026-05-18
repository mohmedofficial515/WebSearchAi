"""Skill: log in to a site with given credentials, with memory-assisted replay."""

from __future__ import annotations

import json

from ..config import settings
from ..core.agent import Agent, TaskResult
from ..utils.logger import log


async def login(
    site_url: str,
    email: str,
    password: str,
    *,
    persist_session: bool = True,
    profile_name: str | None = None,
) -> TaskResult:
    user_data_dir = None
    if persist_session:
        slug = profile_name or email.split("@")[0]
        user_data_dir = settings.output_path / "profiles" / slug
        user_data_dir.mkdir(parents=True, exist_ok=True)

    # ── Memory: look up cached login flow ─────────────────────────────────────
    cached_hint = ""
    try:
        from ..memory import get_memory
        mem = await get_memory()
        cached = await mem.recall_flow(site_url, "login")
        if cached:
            step_count = cached.get("success_count", 0)
            steps_json = json.dumps(cached["flow_data"].get("steps", []), ensure_ascii=False)
            cached_hint = (
                f"\n\nMEMORY — this site was logged into {step_count} time(s) before."
                f"\nCached login steps (reuse selectors/flow if still valid):\n{steps_json}"
                "\nIf you find a session already active, emit 'done' immediately."
            )
            log.info(f"Memory: cached login flow found for {site_url} ({step_count} uses)")
    except Exception as exc:
        log.debug(f"Memory recall skipped: {exc}")

    goal = (
        f"Open {site_url} and log in.\n"
        f"  email/username: {email}\n"
        f"  password: {password}\n"
        "Locate the login link if needed, fill the credentials, submit, "
        "and confirm the dashboard / logged-in state is visible."
        + cached_hint
    )

    async with Agent(user_data_dir=user_data_dir) as agent:
        result = await agent.run(goal)

    # ── Memory: save flow after success ───────────────────────────────────────
    if result.success:
        try:
            from ..memory import get_memory
            mem = await get_memory()
            flow = {
                "steps": result.steps[:10],
                "step_count": len(result.steps),
            }
            await mem.remember_flow(site_url, "login", flow)
            if user_data_dir:
                await mem.remember_login(site_url, str(user_data_dir), email)
            log.info(f"Memory: saved login flow for {site_url} ({len(result.steps)} steps)")
        except Exception as exc:
            log.debug(f"Memory save skipped: {exc}")

    return result
