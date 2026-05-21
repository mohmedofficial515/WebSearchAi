"""HTTP routes for invoking skills (run / signup / login / explore / clone / ...).

Each endpoint enqueues a task via `task_manager` so progress events flow
over the existing `/ws/{task_id}` channel; the response only carries the
task id, not the final result.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ...core.agent import Agent
from ...core.intent_router import Intent, detect_intent
from ...skills.clone import clone as skill_clone
from ...skills.explore import explore as skill_explore
from ...skills.login import login as skill_login
from ...skills.signup import signup as skill_signup
from ..tasks import TaskRecord, task_manager
from .models import (
    CloneBody,
    DesignTokensBody,
    ExploreBody,
    FindComponentsBody,
    LoginBody,
    RunBody,
    SignupBody,
    SiteCloneBody,
    TempSignupBody,
)


router = APIRouter(tags=["skills"])


# ===================== /api/run + dispatcher =====================


@router.post("/api/run")
async def api_run(body: RunBody) -> dict:
    # Smart cache pre-flight: if a virtually identical successful task
    # already exists in the archive, serve it directly. Saves a full
    # browser run for repeat questions.
    if body.use_cache and body.goal and not body.parallel_goals:
        try:
            from ...archive import get_archive
            arc = await get_archive()
            hit = await arc.find_similar(body.goal, threshold=body.cache_threshold)
            if hit:
                full = await arc.get(hit.record.task_id)
                return {
                    "task_id": hit.record.task_id,
                    "status": "succeeded",
                    "cached": True,
                    "cache_score": hit.score,
                    "cache_matched_terms": hit.matched_terms,
                    "result": full.get("result") if full else None,
                }
        except Exception:
            # Cache lookup must never block a real run. Fall through.
            pass

    if body.parallel_goals:
        async def factory(task_id: str) -> Any:
            async with Agent(
                headless=body.headless,
                use_vision=body.use_vision,
            ) as agent:
                results = await agent.run_parallel(body.parallel_goals, task_id=task_id)
                return {"parallel_results": [r.to_dict() for r in results]}

        rec = task_manager.submit("run_parallel", body.model_dump(), factory)
        return {"task_id": rec.task_id, "status": rec.status.value}

    goal = body.goal

    # ── Intent routing ────────────────────────────────────────────────
    # The web UI's hero search posts every natural-language sentence
    # here. We detect skill intents (login / signup / clone / etc.) so
    # the user gets the right action without picking a tab manually.
    intent = detect_intent(goal) if body.auto_route else None
    kind = intent.kind if intent else "research"

    if intent and intent.kind != "research":
        rec = dispatch_skill_intent(intent, body)
        return {
            "task_id": rec.task_id,
            "status": rec.status.value,
            "routed_to": intent.kind,
            "intent": intent.to_dict(),
        }

    async def factory(task_id: str) -> Any:  # type: ignore[no-redef]
        async with Agent(
            headless=body.headless,
            use_vision=body.use_vision,
        ) as agent:
            return await agent.run(goal, task_id=task_id)

    rec = task_manager.submit("run", body.model_dump(), factory)
    return {
        "task_id": rec.task_id,
        "status": rec.status.value,
        "routed_to": kind,
    }


def dispatch_skill_intent(intent: Intent, body: RunBody) -> TaskRecord:
    """Translate a natural-language Intent into a real skill task.

    Returns the TaskManager record so the caller can stream events on
    the same /ws/<task_id> channel the UI is already subscribed to.
    """
    kind = intent.kind
    if kind in ("signup", "temp_signup"):
        from ...skills.signup import signup as _skill_signup
        from ...skills.temp_signup import temp_signup_persist
        site = intent.url or intent.goal

        async def _factory(_task_id: str) -> Any:
            if kind == "temp_signup":
                r = await temp_signup_persist(
                    site,
                    profile_name=intent.params.get("profile_name"),
                    full_name=intent.params.get("full_name"),
                    extra_instructions=intent.goal,
                    headless=body.headless,
                )
                return {
                    "email": r.email,
                    "password": r.password,
                    "site_url": r.site_url,
                    "profile_name": r.profile_name,
                    "session_dir": r.session_dir,
                    "account_card": r.account_card,
                    "verification_link": r.verification_link,
                    "verified": r.verified,
                    "agent_result": r.agent_result,
                }
            r = await _skill_signup(
                site,
                full_name=intent.params.get("full_name"),
                extra_instructions=intent.goal,
            )
            return {
                "email": r.email,
                "password": r.password,
                "site_url": r.site_url,
                "verification_link": r.verification_link,
                "agent_result": r.agent_result.to_dict(),
            }
        return task_manager.submit(kind, {"goal": intent.goal, "url": intent.url}, _factory)

    if kind == "login":
        from ...skills.login import login as _skill_login
        url = intent.url or ""
        email = intent.params.get("email", "")
        password = intent.params.get("password", "")

        async def _factory(_task_id: str) -> Any:
            return await _skill_login(
                url, email, password,
                persist_session=True,
                profile_name=intent.params.get("profile_name"),
            )
        return task_manager.submit("login", {"goal": intent.goal, "url": url}, _factory)

    if kind == "explore":
        from ...skills.explore import explore as _skill_explore
        url = intent.url or ""

        async def _factory(_task_id: str) -> Any:
            r = await _skill_explore(url, intent.params.get("depth_hint") or "thorough")
            return {"site": r.site, "report": r.report, "report_path": r.report_path}
        return task_manager.submit("explore", {"goal": intent.goal, "url": url}, _factory)

    if kind == "clone":
        from ...skills.clone import clone as _skill_clone
        url = intent.url or ""

        async def _factory(_task_id: str) -> Any:
            r = await _skill_clone(url, max_assets=int(intent.params.get("max_assets") or 60))
            return {
                "url": r.url,
                "out_dir": r.out_dir,
                "index_html_path": r.index_html_path,
                "raw_dir": r.raw_dir,
                "media_count": r.media_count,
                "css_count": r.css_count,
                "js_count": r.js_count,
                "library_swaps": r.library_swaps,
                "dropped_count": len(r.dropped_assets),
            }
        return task_manager.submit("clone", {"goal": intent.goal, "url": url}, _factory)

    if kind == "components":
        from ...skills.find_components import find_components
        query = intent.params.get("query") or intent.goal

        async def _factory(_task_id: str) -> Any:
            r = await find_components(
                query,
                max_pages=int(intent.params.get("max_pages") or 5),
                max_variants_per_page=int(intent.params.get("max_variants_per_page") or 3),
                headless=True if body.headless is None else body.headless,
            )
            return r.to_dict()
        return task_manager.submit(
            "find_components", {"goal": intent.goal, "query": query}, _factory
        )

    if kind == "design_tokens":
        from ...skills.design_tokens import extract_design_tokens
        url = intent.url or ""

        async def _factory(_task_id: str) -> Any:
            tokens = await extract_design_tokens(
                url,
                headless=True if body.headless is None else body.headless,
                wait_seconds=float(intent.params.get("wait_seconds") or 2.0),
            )
            return tokens.to_dict()
        return task_manager.submit(
            "design_tokens", {"goal": intent.goal, "url": url}, _factory
        )

    # Unknown kind shouldn't reach here, but fall back to research.
    async def _factory(task_id: str) -> Any:
        async with Agent(headless=body.headless, use_vision=body.use_vision) as agent:
            return await agent.run(intent.goal, task_id=task_id)
    return task_manager.submit("run", {"goal": intent.goal}, _factory)


# ===================== Individual skill endpoints =====================


@router.post("/api/signup")
async def api_signup(body: SignupBody) -> dict:
    async def factory(_task_id: str) -> Any:
        result = await skill_signup(
            body.site_url,
            full_name=body.full_name,
            extra_instructions=body.extra_instructions,
        )
        return {
            "email": result.email,
            "password": result.password,
            "site_url": result.site_url,
            "verification_link": result.verification_link,
            "agent_result": result.agent_result.to_dict(),
        }

    rec = task_manager.submit("signup", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/login")
async def api_login(body: LoginBody) -> dict:
    async def factory(_task_id: str) -> Any:
        return await skill_login(
            body.site_url,
            body.email,
            body.password,
            persist_session=body.persist_session,
            profile_name=body.profile_name,
        )

    rec = task_manager.submit("login", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/explore")
async def api_explore(body: ExploreBody) -> dict:
    async def factory(_task_id: str) -> Any:
        result = await skill_explore(body.site_url, body.depth_hint)
        return {
            "site": result.site,
            "report": result.report,
            "report_path": result.report_path,
        }

    rec = task_manager.submit("explore", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/site-clone")
async def api_site_clone(body: SiteCloneBody) -> dict:
    """Crawl an entire site with BFS and save HTML for every page."""
    from ...skills.site_clone import site_clone as skill_site_clone

    async def factory(_task_id: str) -> Any:
        result = await skill_site_clone(
            body.url,
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            take_screenshots=body.take_screenshots,
            headless=body.headless,
        )
        return result.to_dict()

    rec = task_manager.submit("site_clone", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/clone")
async def api_clone(body: CloneBody) -> dict:
    async def factory(_task_id: str) -> Any:
        result = await skill_clone(body.url, max_assets=body.max_assets)
        return {
            "url": result.url,
            "out_dir": result.out_dir,
            "index_html_path": result.index_html_path,
            "raw_dir": result.raw_dir,
            "media_count": result.media_count,
            "css_count": result.css_count,
            "js_count": result.js_count,
            "library_swaps": result.library_swaps,
            "dropped_count": len(result.dropped_assets),
        }

    rec = task_manager.submit("clone", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/temp-signup")
async def api_temp_signup(body: TempSignupBody) -> dict:
    """Sign up + persist the browser session for permanent reuse."""
    from ...skills.temp_signup import temp_signup_persist

    async def factory(_task_id: str) -> Any:
        result = await temp_signup_persist(
            body.site_url,
            profile_name=body.profile_name,
            full_name=body.full_name,
            extra_instructions=body.extra_instructions,
            headless=body.headless,
        )
        return {
            "email": result.email,
            "password": result.password,
            "site_url": result.site_url,
            "profile_name": result.profile_name,
            "session_dir": result.session_dir,
            "account_card": result.account_card,
            "verification_link": result.verification_link,
            "verified": result.verified,
            "agent_result": result.agent_result,
        }

    rec = task_manager.submit("temp_signup", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.get("/api/accounts")
async def api_accounts_list() -> list[dict]:
    """List every persistent account the agent has created."""
    from ...skills.temp_signup import list_accounts
    return list_accounts()


@router.delete("/api/accounts/{profile_name}")
async def api_accounts_forget(profile_name: str) -> dict:
    from ...skills.temp_signup import forget_account
    ok = forget_account(profile_name)
    if not ok:
        raise HTTPException(404, "profile not found")
    return {"ok": True, "profile_name": profile_name}


@router.post("/api/find-components")
async def api_find_components(body: FindComponentsBody) -> dict:
    """Designer/dev skill: search → screenshot → gallery."""
    from ...skills.find_components import find_components

    async def factory(_task_id: str) -> Any:
        result = await find_components(
            body.query,
            max_pages=body.max_pages,
            max_variants_per_page=body.max_variants_per_page,
            headless=body.headless,
        )
        return result.to_dict()

    rec = task_manager.submit("find_components", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@router.post("/api/design-tokens")
async def api_design_tokens(body: DesignTokensBody) -> dict:
    """Designer skill: extract palette / typography / spacing from a URL."""
    from ...skills.design_tokens import extract_design_tokens

    async def factory(_task_id: str) -> Any:
        tokens = await extract_design_tokens(
            body.url,
            headless=body.headless,
            wait_seconds=body.wait_seconds,
        )
        return tokens.to_dict()

    rec = task_manager.submit("design_tokens", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}
