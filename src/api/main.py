"""FastAPI application: REST endpoints + WebSocket stream + Web UI."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Windows-only: ensure subprocess support is available to whichever
# event loop ends up running this app. Patchright/Playwright launches
# Chrome via `create_subprocess_exec`, which raises NotImplementedError
# under SelectorEventLoop (the default in uvicorn's --reload worker).
# Set the policy at import time so it sticks even when the loop hasn't
# been created yet. No-op everywhere else.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:  # noqa: BLE001
        # If someone else already set a policy we don't fight them —
        # they presumably know what they're doing.
        pass

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import settings
from ..core.agent import Agent
from ..core.intent_router import detect_intent
from ..skills.clone import clone as skill_clone
from ..skills.explore import explore as skill_explore
from ..skills.login import login as skill_login
from ..skills.signup import signup as skill_signup
from ..utils.event_bus import bus
from .auth import router as auth_router
from .routes.artifacts import router as artifacts_router
from .routes.chat import router as chat_router
from .routes.continuation import router as continuation_router
from .routes.intent import router as intent_router
from .routes.pipelines import router as pipelines_router
from .routes.uploads import router as uploads_router
from .tasks import task_manager


ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"


app = FastAPI(
    title="WebSearchAi",
    version="0.1.0",
    description="Professional AI-driven browser automation",
)

app.include_router(auth_router)
app.include_router(intent_router)
app.include_router(chat_router)
app.include_router(uploads_router)
app.include_router(artifacts_router)
app.include_router(continuation_router)
app.include_router(pipelines_router)

if (WEB_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

# React chat SPA — served at /chat (built to web/static/chat/)
_CHAT_DIR = WEB_DIR / "static" / "chat"
if _CHAT_DIR.exists():
    app.mount("/chat", StaticFiles(directory=str(_CHAT_DIR), html=True), name="chat")

if (settings.output_path).exists():
    app.mount(
        "/artifacts",
        StaticFiles(directory=str(settings.output_path)),
        name="artifacts",
    )


# ===================== Models =====================


class RunBody(BaseModel):
    goal: str = Field("", description="Natural-language goal for the agent")
    parallel_goals: list[str] = Field(default_factory=list, description="Run multiple goals concurrently")
    headless: bool | None = None
    use_vision: bool = True
    # Cache short-circuit is OFF by default — fresh runs are the spec.
    # Set use_cache=true and provide a cache_threshold to opt back into
    # returning a near-identical past task without a browser run.
    use_cache: bool = False
    cache_threshold: float = 0.85
    # When true, route the goal through the intent classifier so plain
    # English/Arabic phrases like "ادخل إلى github.com" dispatch to the
    # right skill (login/signup/clone/...) instead of always research.
    auto_route: bool = True


class SignupBody(BaseModel):
    site_url: str
    full_name: str | None = None
    extra_instructions: str = ""


class LoginBody(BaseModel):
    site_url: str
    email: str
    password: str
    persist_session: bool = True
    profile_name: str | None = None


class ExploreBody(BaseModel):
    site_url: str
    depth_hint: str = "thorough"


class CloneBody(BaseModel):
    url: str
    max_assets: int = 60


class SiteCloneBody(BaseModel):
    url: str
    max_pages: int = 50
    max_depth: int = 3
    take_screenshots: bool = False
    headless: bool = True


class TempSignupBody(BaseModel):
    site_url: str
    profile_name: str | None = None
    full_name: str | None = None
    extra_instructions: str = ""
    headless: bool | None = None


class FindComponentsBody(BaseModel):
    query: str
    max_pages: int = 5                  # how many search results to visit
    max_variants_per_page: int = 3      # how many components to extract per page
    headless: bool = True


class DesignTokensBody(BaseModel):
    url: str
    headless: bool = True
    wait_seconds: float = 2.0


class VisualBaselineBody(BaseModel):
    url: str
    name: str
    headless: bool = True


class VisualCompareBody(BaseModel):
    url: str
    name: str
    threshold: float = 0.01
    headless: bool = True


# ===================== UI =====================


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/chat/", status_code=301)


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "version": "0.1.0"}


# ===================== Skills (sync REST) =====================


@app.post("/api/run")
async def api_run(body: RunBody) -> dict:
    # Smart cache pre-flight: if a virtually identical successful task
    # already exists in the archive, serve it directly. Saves a full
    # browser run for repeat questions.
    if body.use_cache and body.goal and not body.parallel_goals:
        try:
            from ..archive import get_archive
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
        async def factory(task_id: str):
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
        rec = _dispatch_skill_intent(intent, body)
        return {
            "task_id": rec.task_id,
            "status": rec.status.value,
            "routed_to": intent.kind,
            "intent": intent.to_dict(),
        }

    async def factory(task_id: str):  # type: ignore[no-redef]
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


def _dispatch_skill_intent(intent, body: RunBody):
    """Translate a natural-language Intent into a real skill task.

    Returns the TaskManager record so the caller can stream events on
    the same /ws/<task_id> channel the UI is already subscribed to.
    """
    kind = intent.kind
    if kind in ("signup", "temp_signup"):
        from ..skills.temp_signup import temp_signup_persist
        from ..skills.signup import signup as _skill_signup
        site = intent.url or intent.goal

        async def _factory(_task_id: str):
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
        from ..skills.login import login as _skill_login
        url = intent.url or ""
        email = intent.params.get("email", "")
        password = intent.params.get("password", "")
        async def _factory(_task_id: str):
            return await _skill_login(
                url, email, password,
                persist_session=True,
                profile_name=intent.params.get("profile_name"),
            )
        return task_manager.submit("login", {"goal": intent.goal, "url": url}, _factory)

    if kind == "explore":
        from ..skills.explore import explore as _skill_explore
        url = intent.url or ""
        async def _factory(_task_id: str):
            r = await _skill_explore(url, intent.params.get("depth_hint") or "thorough")
            return {"site": r.site, "report": r.report, "report_path": r.report_path}
        return task_manager.submit("explore", {"goal": intent.goal, "url": url}, _factory)

    if kind == "clone":
        from ..skills.clone import clone as _skill_clone
        url = intent.url or ""
        async def _factory(_task_id: str):
            r = await _skill_clone(url, max_assets=int(intent.params.get("max_assets") or 60))
            return {
                "url": r.url,
                "raw_dir": r.raw_dir,
                "rebuilt_html_path": r.rebuilt_html_path,
                "assets": r.assets,
            }
        return task_manager.submit("clone", {"goal": intent.goal, "url": url}, _factory)

    if kind == "components":
        from ..skills.find_components import find_components
        query = intent.params.get("query") or intent.goal
        async def _factory(_task_id: str):
            r = await find_components(
                query,
                max_pages=int(intent.params.get("max_pages") or 5),
                max_variants_per_page=int(intent.params.get("max_variants_per_page") or 3),
                headless=True if body.headless is None else body.headless,
            )
            return r.to_dict()
        return task_manager.submit("find_components", {"goal": intent.goal, "query": query}, _factory)

    if kind == "design_tokens":
        from ..skills.design_tokens import extract_design_tokens
        url = intent.url or ""
        async def _factory(_task_id: str):
            tokens = await extract_design_tokens(
                url,
                headless=True if body.headless is None else body.headless,
                wait_seconds=float(intent.params.get("wait_seconds") or 2.0),
            )
            return tokens.to_dict()
        return task_manager.submit("design_tokens", {"goal": intent.goal, "url": url}, _factory)

    # Unknown kind shouldn't reach here, but fall back to research.
    async def _factory(task_id: str):
        async with Agent(headless=body.headless, use_vision=body.use_vision) as agent:
            return await agent.run(intent.goal, task_id=task_id)
    return task_manager.submit("run", {"goal": intent.goal}, _factory)


@app.post("/api/signup")
async def api_signup(body: SignupBody) -> dict:
    async def factory(_task_id: str):
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


@app.post("/api/login")
async def api_login(body: LoginBody) -> dict:
    async def factory(_task_id: str):
        return await skill_login(
            body.site_url,
            body.email,
            body.password,
            persist_session=body.persist_session,
            profile_name=body.profile_name,
        )

    rec = task_manager.submit("login", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@app.post("/api/explore")
async def api_explore(body: ExploreBody) -> dict:
    async def factory(_task_id: str):
        result = await skill_explore(body.site_url, body.depth_hint)
        return {
            "site": result.site,
            "report": result.report,
            "report_path": result.report_path,
        }

    rec = task_manager.submit("explore", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@app.post("/api/site-clone")
async def api_site_clone(body: SiteCloneBody) -> dict:
    """Crawl an entire site with BFS and save HTML for every page."""
    from ..skills.site_clone import site_clone as skill_site_clone

    async def factory(_task_id: str):
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


@app.post("/api/clone")
async def api_clone(body: CloneBody) -> dict:
    async def factory(_task_id: str):
        result = await skill_clone(body.url, max_assets=body.max_assets)
        return {
            "url": result.url,
            "raw_dir": result.raw_dir,
            "rebuilt_html_path": result.rebuilt_html_path,
            "assets": result.assets,
        }

    rec = task_manager.submit("clone", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@app.post("/api/temp-signup")
async def api_temp_signup(body: TempSignupBody) -> dict:
    """Sign up + persist the browser session for permanent reuse."""
    from ..skills.temp_signup import temp_signup_persist

    async def factory(_task_id: str):
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


@app.get("/api/accounts")
async def api_accounts_list() -> list[dict]:
    """List every persistent account the agent has created."""
    from ..skills.temp_signup import list_accounts
    return list_accounts()


@app.delete("/api/accounts/{profile_name}")
async def api_accounts_forget(profile_name: str) -> dict:
    from ..skills.temp_signup import forget_account
    ok = forget_account(profile_name)
    if not ok:
        raise HTTPException(404, "profile not found")
    return {"ok": True, "profile_name": profile_name}


@app.post("/api/find-components")
async def api_find_components(body: FindComponentsBody) -> dict:
    """Designer/dev skill: search → screenshot → gallery."""
    from ..skills.find_components import find_components

    async def factory(_task_id: str):
        result = await find_components(
            body.query,
            max_pages=body.max_pages,
            max_variants_per_page=body.max_variants_per_page,
            headless=body.headless,
        )
        return result.to_dict()

    rec = task_manager.submit("find_components", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


@app.post("/api/design-tokens")
async def api_design_tokens(body: DesignTokensBody) -> dict:
    """Designer skill: extract palette / typography / spacing from a URL."""
    from ..skills.design_tokens import extract_design_tokens

    async def factory(_task_id: str):
        tokens = await extract_design_tokens(
            body.url,
            headless=body.headless,
            wait_seconds=body.wait_seconds,
        )
        return tokens.to_dict()

    rec = task_manager.submit("design_tokens", body.model_dump(), factory)
    return {"task_id": rec.task_id, "status": rec.status.value}


# ===================== Task management =====================


@app.get("/api/tasks")
async def list_tasks(
    history: bool = False,
    limit: int = 100,
    kind: str | None = None,
) -> list[dict]:
    """List tasks. Pass ?history=true to include persisted past-session records."""
    if history:
        return await task_manager.list_history(limit=limit, kind=kind)
    return task_manager.list()


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    rec = task_manager.get(task_id)
    if rec:
        return rec.to_dict()
    # Fall back to persistent store for completed tasks from prior sessions
    from ..storage import get_task_store
    store = await get_task_store()
    stored = await store.load_task(task_id)
    if not stored:
        raise HTTPException(404, "task not found")
    return stored


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str) -> dict:
    ok = task_manager.cancel(task_id)
    if not ok:
        raise HTTPException(409, "cannot cancel task")
    return {"ok": True}


@app.get("/api/tasks/{task_id}/events")
async def get_task_events(task_id: str) -> list[dict]:
    return [e.to_dict() for e in bus.history(task_id)]


@app.get("/api/tasks/{task_id}/report")
async def get_task_report(task_id: str) -> dict:
    """Return the Arabic Markdown report for a task.

    Looks first for the pre-rendered `report.ar.md` written by the
    research flow; if missing (legacy task), regenerates on the fly
    from the stored result JSON.
    """
    from ..config import settings
    from ..reports import render_arabic_report
    from ..storage import get_task_store

    artifacts = settings.output_path / "sessions" / task_id
    report_file = artifacts / "report.ar.md"
    if report_file.exists():
        return {"task_id": task_id, "markdown": report_file.read_text(encoding="utf-8"), "source": "file"}

    # Fallback: regenerate from the live task manager or persistent store.
    result_dict: dict | None = None
    rec = task_manager.get(task_id)
    if rec and rec.result and isinstance(rec.result, dict):
        result_dict = rec.result
    if result_dict is None:
        store = await get_task_store()
        stored = await store.load_task(task_id)
        if stored and isinstance(stored.get("result"), dict):
            result_dict = stored["result"]
    if result_dict is None:
        raise HTTPException(404, "no result available for this task")
    return {"task_id": task_id, "markdown": render_arabic_report(result_dict), "source": "generated"}


# ===================== Library skills =====================


class GoogleSearchBody(BaseModel):
    query: str
    max_results: int = 10


class YouTubeSearchBody(BaseModel):
    query: str
    max_results: int = 10


class LinkedInBody(BaseModel):
    url: str


@app.post("/api/library/google")
async def api_google_search(body: GoogleSearchBody) -> dict:
    """Search Google — deterministic, zero LLM calls."""
    from ..skills.library import google_search
    result = await google_search(body.query, max_results=body.max_results)
    return result.to_dict()


@app.post("/api/library/youtube")
async def api_youtube_search(body: YouTubeSearchBody) -> dict:
    """Search YouTube — deterministic, zero LLM calls."""
    from ..skills.library import youtube_search
    result = await youtube_search(body.query, max_results=body.max_results)
    return result.to_dict()


@app.post("/api/library/linkedin")
async def api_linkedin_profile(body: LinkedInBody) -> dict:
    """Extract a LinkedIn profile — deterministic, zero LLM calls."""
    from ..skills.library import linkedin_extract_profile
    result = await linkedin_extract_profile(body.url)
    return result.to_dict()


# ===================== Visual Testing =====================


@app.post("/api/visual-test/baseline")
async def api_visual_baseline(body: VisualBaselineBody) -> dict:
    """Capture a visual baseline screenshot for *name*."""
    from ..skills.visual_test import capture_baseline
    path = await capture_baseline(body.url, body.name, headless=body.headless)
    return {"ok": True, "name": body.name, "path": str(path)}


@app.post("/api/visual-test/compare")
async def api_visual_compare(body: VisualCompareBody) -> dict:
    """Compare a fresh screenshot against the stored baseline *name*."""
    from ..skills.visual_test import compare
    result = await compare(
        body.url, body.name,
        threshold=body.threshold,
        headless=body.headless,
    )
    return result.to_dict()


@app.get("/api/visual-test/baselines")
async def api_visual_list_baselines() -> list[dict]:
    """List all stored visual baselines."""
    from ..skills.visual_test import list_baselines
    return list_baselines()


@app.delete("/api/visual-test/baselines/{name}")
async def api_visual_delete_baseline(name: str) -> dict:
    """Delete the baseline *name*."""
    from ..skills.visual_test import delete_baseline
    ok = delete_baseline(name)
    if not ok:
        raise HTTPException(404, f"Baseline '{name}' not found")
    return {"ok": True, "deleted": name}


# ===================== Memory =====================


@app.get("/api/memory/sites")
async def memory_list_sites() -> list[dict]:
    """List all sites stored in long-term agent memory."""
    from ..memory import get_memory
    store = await get_memory()
    return await store.list_sites()


@app.delete("/api/memory/sites")
async def memory_forget_site(url: str) -> dict:
    """Remove a site and all its data (flows, vectors, logins) from memory."""
    from ..memory import get_memory
    store = await get_memory()
    await store.forget_site(url)
    return {"ok": True, "forgotten": url}


@app.get("/api/memory/search")
async def memory_search(query: str, k: int = 5) -> list[dict]:
    """Semantic search over agent memory (requires MISTRAL_API_KEY)."""
    if not settings.mistral_api_key:
        raise HTTPException(400, "MISTRAL_API_KEY not configured")
    from ..memory import MemoryRecall, get_memory
    store = await get_memory()
    recall = MemoryRecall(store, settings.mistral_api_key)
    return await recall.search(query, k=k)


# ===================== Task Archive (smart re-use) =====================


@app.get("/api/archive")
async def archive_list(limit: int = 50, success_only: bool = True) -> list[dict]:
    """Recent archived tasks (newest first)."""
    from ..archive import get_archive
    arc = await get_archive()
    records = await arc.list(limit=limit, success_only=success_only)
    return [r.to_dict() for r in records]


@app.get("/api/archive/search")
async def archive_search(q: str, limit: int = 10, min_score: float = 0.05) -> dict:
    """Rank archived tasks by TF-IDF similarity to the query.

    Returns: { query, matches: [{task_id, goal, summary, score, matched_terms, ...}] }
    """
    from ..archive import get_archive
    arc = await get_archive()
    matches = await arc.search(q, limit=limit, min_score=min_score)
    return {"query": q, "matches": [m.to_dict() for m in matches]}


class ArchiveCheckBody(BaseModel):
    goal: str = Field(..., description="The new goal the user is about to run.")
    threshold: float = Field(0.55, ge=0.0, le=1.0)


@app.post("/api/archive/check")
async def archive_check(body: ArchiveCheckBody) -> dict:
    """Pre-flight check: is there an archived task that already answers
    this goal? Used by the UI to offer "reuse this past result" before
    spinning up the browser.

    Threshold guide:
      0.95+ → effectively identical wording  (auto-suggest reuse)
      0.80  → same intent, different phrasing  (prompt the user)
      0.55  → same topic; surface as "did you mean…"
    """
    from ..archive import get_archive
    arc = await get_archive()
    hit = await arc.find_similar(body.goal, threshold=body.threshold)
    if not hit:
        return {"match": None}
    return {"match": hit.to_dict()}


@app.get("/api/archive/{task_id}")
async def archive_get(task_id: str) -> dict:
    from ..archive import get_archive
    arc = await get_archive()
    rec = await arc.get(task_id)
    if not rec:
        raise HTTPException(404, f"Archive entry {task_id} not found")
    return rec


@app.delete("/api/archive/{task_id}")
async def archive_delete(task_id: str) -> dict:
    from ..archive import get_archive
    arc = await get_archive()
    ok = await arc.delete(task_id)
    if not ok:
        raise HTTPException(404, f"Archive entry {task_id} not found")
    return {"ok": True, "deleted": task_id}


# ===================== WebSocket stream =====================


@app.websocket("/ws/{task_id}")
async def ws_stream(ws: WebSocket, task_id: str) -> None:
    await ws.accept()
    q = bus.subscribe(task_id)
    try:
        for ev in bus.history(task_id):
            await ws.send_text(json.dumps(ev.to_dict(), ensure_ascii=False, default=str))
        while True:
            ev = await q.get()
            await ws.send_text(json.dumps(ev.to_dict(), ensure_ascii=False, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(task_id, q)


# ===================== Plugin / skill registry =====================


@app.get("/api/plugins")
async def api_list_plugins() -> list[dict]:
    """Return all discovered async skills/plugins."""
    from ..skills.plugin_loader import plugin_loader
    return [s.to_dict() for s in plugin_loader.list()]


@app.get("/api/plugins/{name}")
async def api_get_plugin(name: str) -> dict:
    """Return metadata for a single plugin/skill by name."""
    from ..skills.plugin_loader import plugin_loader
    skill = plugin_loader.get(name)
    if skill is None:
        raise HTTPException(404, f"plugin '{name}' not found")
    return skill.to_dict()


# ===================== Static helpers =====================


@app.get("/api/artifact/{task_id}/{filename}")
async def get_artifact(task_id: str, filename: str) -> FileResponse:
    p = settings.output_path / "sessions" / task_id / filename
    if not p.exists():
        raise HTTPException(404, "artifact not found")
    return FileResponse(str(p))


# ===================== LLM Costs =====================


@app.get("/api/costs")
async def api_costs_summary() -> list[dict]:
    """Daily cost summary grouped by UTC date."""
    from ..llm.costs import cost_tracker
    return cost_tracker.daily_summary()


@app.get("/api/costs/entries")
async def api_costs_entries(limit: int = 100) -> list[dict]:
    """Recent raw cost entries (most recent last)."""
    from ..llm.costs import cost_tracker
    entries = cost_tracker.read_entries()
    return [e.to_dict() for e in entries[-limit:]]


# ===================== Provider Management =====================

# Model metadata: stars (1-5), speed (fast/medium/slow/local), vision support
_MODEL_META: dict[str, dict] = {
    # ── Groq ──
    "llama-3.1-8b-instant":            {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "llama-3.3-70b-versatile":         {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "llama-3.2-11b-vision-preview":    {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 128},
    "llama-3.2-90b-vision-preview":    {"stars": 5, "speed": "medium", "vision": True,  "ctx_k": 128},
    "llama-3.2-3b-preview":            {"stars": 2, "speed": "fast",   "vision": False, "ctx_k": 128},
    "gemma2-9b-it":                    {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 8},
    # ── Gemini ──
    "gemini-2.0-flash":                {"stars": 5, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-2.5-flash-preview-05-20":  {"stars": 5, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-1.5-flash":                {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-2.0-flash-exp":            {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-1.5-pro":                  {"stars": 5, "speed": "medium", "vision": True,  "ctx_k": 2097},
    # ── Cohere ──
    "command-r":                       {"stars": 3, "speed": "medium", "vision": False, "ctx_k": 128},
    "command-r-plus":                  {"stars": 4, "speed": "medium", "vision": False, "ctx_k": 128},
    "command-r7b-12-2024":             {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "command-a-03-2025":               {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 256},
    # ── OpenRouter free ──
    "meta-llama/llama-3.1-8b-instruct:free":     {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "meta-llama/llama-3.2-3b-instruct:free":     {"stars": 2, "speed": "fast",   "vision": False, "ctx_k": 128},
    "meta-llama/llama-3.3-70b-instruct:free":    {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "google/gemma-2-9b-it:free":                 {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 8},
    "google/gemma-3-12b-it:free":                {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 128},
    "mistralai/mistral-7b-instruct:free":        {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "microsoft/phi-3-mini-128k-instruct:free":   {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "qwen/qwen-2-7b-instruct:free":              {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "qwen/qwen3-8b:free":                        {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 128},
    "deepseek/deepseek-r1:free":                 {"stars": 5, "speed": "slow",   "vision": False, "ctx_k": 64},
    "deepseek/deepseek-chat-v3-0324:free":       {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 64},
    "nousresearch/hermes-3-llama-3.1-405b:free": {"stars": 5, "speed": "slow",   "vision": False, "ctx_k": 128},
    # ── Mistral ──
    "mistral-small-latest":  {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "mistral-large-latest":  {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "open-mistral-7b":       {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "open-mixtral-8x7b":     {"stars": 4, "speed": "medium", "vision": False, "ctx_k": 32},
    "codestral-latest":      {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 256},
    "mistral-nemo":          {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 128},
    "pixtral-large-latest":  {"stars": 5, "speed": "slow",   "vision": True,  "ctx_k": 128},
    # ── OpenAI ──
    "gpt-4o-mini": {"stars": 4, "speed": "fast",   "vision": True, "ctx_k": 128},
    "gpt-4o":      {"stars": 5, "speed": "medium", "vision": True, "ctx_k": 128},
    # ── Anthropic ──
    "claude-haiku-4-5-20251001": {"stars": 4, "speed": "fast",   "vision": True, "ctx_k": 200},
    "claude-sonnet-4-6":         {"stars": 5, "speed": "medium", "vision": True, "ctx_k": 200},
    "claude-opus-4-7":           {"stars": 5, "speed": "slow",   "vision": True, "ctx_k": 200},
    # ── Ollama local ──
    "llama3.2":  {"stars": 3, "speed": "local", "vision": True,  "ctx_k": 128},
    "llama3.1":  {"stars": 4, "speed": "local", "vision": False, "ctx_k": 128},
    "mistral":   {"stars": 3, "speed": "local", "vision": False, "ctx_k": 32},
    "phi3":      {"stars": 3, "speed": "local", "vision": False, "ctx_k": 128},
    "gemma2":    {"stars": 3, "speed": "local", "vision": False, "ctx_k": 8},
    "qwen2.5":   {"stars": 4, "speed": "local", "vision": False, "ctx_k": 128},
}

_PROVIDER_CATALOG = [
    {
        "name": "groq",
        "label": "Groq",
        "emoji": "⚡",
        "tier": "free",
        "desc": "Ultra-fast open-source inference — fastest free option",
        "free_info": "14,400 req/day · 6K tokens/min",
        "signup_url": "https://console.groq.com",
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
            "llama-3.2-3b-preview",
            "gemma2-9b-it",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "groq_api_key",
        "model_field": "groq_text_model",
        "key_placeholder": "gsk_...",
    },
    {
        "name": "gemini",
        "label": "Google Gemini",
        "emoji": "✨",
        "tier": "free",
        "desc": "Google's multimodal AI — vision + 1M token context",
        "free_info": "1,500 req/day · 15 req/min",
        "signup_url": "https://aistudio.google.com",
        "models": [
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-05-20",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "gemini_api_key",
        "model_field": "gemini_text_model",
        "key_placeholder": "AIza...",
    },
    {
        "name": "cohere",
        "label": "Cohere",
        "emoji": "🧩",
        "tier": "free",
        "desc": "Best free embeddings — 100+ language multilingual model",
        "free_info": "1,000 calls/month (Trial key)",
        "signup_url": "https://cohere.com",
        "models": [
            "command-r",
            "command-r-plus",
            "command-r7b-12-2024",
            "command-a-03-2025",
        ],
        "supports_vision": False,
        "supports_embed": True,
        "key_field": "cohere_api_key",
        "model_field": "cohere_text_model",
        "key_placeholder": "...",
    },
    {
        "name": "openrouter",
        "label": "OpenRouter",
        "emoji": "🔀",
        "tier": "free",
        "desc": "Aggregates 200+ models — many permanently free (:free suffix). Models loaded live from API.",
        "free_info": "Unlimited on :free models",
        "signup_url": "https://openrouter.ai",
        "models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-2-9b-it:free",
            "google/gemma-3-12b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "microsoft/phi-3-mini-128k-instruct:free",
            "qwen/qwen-2-7b-instruct:free",
            "qwen/qwen3-8b:free",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "openrouter_api_key",
        "model_field": "openrouter_text_model",
        "key_placeholder": "sk-or-...",
    },
    {
        "name": "mistral",
        "label": "Mistral",
        "emoji": "🌬️",
        "tier": "paid",
        "desc": "Best-in-class European AI — vision + embeddings",
        "free_info": "Free trial credits at sign-up",
        "signup_url": "https://console.mistral.ai",
        "models": [
            "mistral-small-latest",
            "mistral-large-latest",
            "open-mistral-7b",
            "open-mixtral-8x7b",
            "codestral-latest",
            "mistral-nemo",
            "pixtral-large-latest",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "mistral_api_key",
        "model_field": "mistral_text_model",
        "key_placeholder": "...",
    },
    {
        "name": "openai",
        "label": "OpenAI",
        "emoji": "🤖",
        "tier": "paid",
        "desc": "GPT-4o family — industry standard",
        "free_info": "Pay-per-use, no free tier",
        "signup_url": "https://platform.openai.com",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "openai_api_key",
        "model_field": None,
        "key_placeholder": "sk-...",
    },
    {
        "name": "anthropic",
        "label": "Anthropic",
        "emoji": "🧠",
        "tier": "paid",
        "desc": "Claude family — best for long documents & reasoning",
        "free_info": "Pay-per-use, no free tier",
        "signup_url": "https://console.anthropic.com",
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-7",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "anthropic_api_key",
        "model_field": None,
        "key_placeholder": "sk-ant-...",
    },
    {
        "name": "ollama",
        "label": "Ollama (Local)",
        "emoji": "🦙",
        "tier": "local",
        "desc": "Run any open-source model 100% locally — no API key needed",
        "free_info": "Completely free — runs on your machine",
        "signup_url": "https://ollama.com",
        "models": [
            "llama3.2",
            "llama3.1",
            "mistral",
            "phi3",
            "gemma2",
            "qwen2.5",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": None,
        "model_field": None,
        "key_placeholder": None,
    },
]


def _key_hint(val: str) -> str:
    """Return first 6 chars + '...' or empty string."""
    if not val:
        return ""
    return val[:6] + "..." if len(val) > 6 else val


@app.get("/api/providers")
async def api_list_providers() -> dict:
    """Return provider catalog with current configuration status."""
    result = []
    for meta in _PROVIDER_CATALOG:
        key_field = meta["key_field"]
        model_field = meta["model_field"]
        current_key: str = getattr(settings, str(key_field), "") if key_field else ""
        current_model: str = getattr(settings, str(model_field), "") if model_field else ""
        # Enrich each model in the models list with metadata
        enriched_models = []
        raw_models: list[str] = meta["models"]  # type: ignore[assignment]
        for m in raw_models:
            mm = _MODEL_META.get(m, {"stars": 3, "speed": "medium", "vision": meta.get("supports_vision", False), "ctx_k": 0})
            enriched_models.append({
                "id": m,
                "stars": mm["stars"],
                "speed": mm["speed"],
                "vision": mm["vision"],
                "ctx_k": mm["ctx_k"],
            })
        entry = {
            **meta,
            "models": enriched_models,
            "is_configured": bool(current_key) or meta["name"] == "ollama",
            "key_hint": _key_hint(current_key),
            "current_model": current_model,
        }
        result.append(entry)
    return {"active": settings.llm_provider, "providers": result}


_ALLOWED_SETTINGS = {
    "llm_provider",
    "mistral_api_key", "mistral_text_model",
    "openai_api_key",
    "anthropic_api_key",
    "groq_api_key", "groq_text_model",
    "gemini_api_key", "gemini_text_model",
    "cohere_api_key", "cohere_text_model",
    "openrouter_api_key", "openrouter_text_model",
    "ollama_base_url",
}


def _update_dotenv(updates: dict[str, str]) -> None:
    """Write/update key=VALUE pairs in .env — creates file if absent."""
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().upper()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.post("/api/providers/save")
async def api_save_providers(body: dict) -> dict:
    """Persist provider settings to .env and update in-memory config."""
    safe = {k: str(v) for k, v in body.items() if k in _ALLOWED_SETTINGS and v is not None}
    _update_dotenv({k.upper(): v for k, v in safe.items()})
    for k, v in safe.items():
        try:
            setattr(settings, k, v)
        except Exception:
            pass
    return {"ok": True, "saved": sorted(safe.keys())}


@app.get("/api/providers/test/{name}")
async def api_test_provider(name: str) -> dict:
    """Quick connectivity test — returns actual model reply."""
    import time
    from ..llm.providers.auto import make_named_provider

    try:
        provider = make_named_provider(name, settings)
        model_name = getattr(provider, "_text_model", name)
        start = time.time()
        reply = await provider.chat(
            [{"role": "user", "content": "Say hello and tell me your model name in one short sentence."}]
        )
        ms = int((time.time() - start) * 1000)
        await provider.close()
        return {"ok": True, "latency_ms": ms, "model": model_name, "reply": reply}
    except NotImplementedError as exc:
        return {"ok": False, "error": f"Not configured: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/providers/{name}/models")
async def api_provider_models(name: str) -> dict:
    """Fetch live model list from the named provider's API."""
    try:
        if name == "openrouter":
            return await api_openrouter_models()

        if name == "groq":
            key = getattr(settings, "groq_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                data = r.json()
            models = [
                {"id": m["id"], "name": m.get("id", ""), "context_length": 0, "supports_vision": "vision" in m.get("id", "").lower()}
                for m in data.get("data", [])
                if not m.get("id", "").endswith("-whisper") and "whisper" not in m.get("id", "").lower()
            ]
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "gemini":
            key = getattr(settings, "gemini_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                )
                r.raise_for_status()
                data = r.json()
            models = []
            for m in data.get("models", []):
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                raw_name = m.get("name", "").replace("models/", "")
                models.append({
                    "id": raw_name,
                    "name": m.get("displayName", raw_name),
                    "context_length": m.get("inputTokenLimit", 0),
                    "supports_vision": True,
                })
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "cohere":
            key = getattr(settings, "cohere_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.cohere.com/v1/models",
                    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
            models = []
            for m in data.get("models", []):
                endpoints = m.get("endpoints", [])
                if "chat" not in endpoints and "generate" not in endpoints:
                    continue
                models.append({
                    "id": m.get("name", ""),
                    "name": m.get("name", ""),
                    "context_length": m.get("context_length", 0),
                    "supports_vision": False,
                })
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "mistral":
            key = getattr(settings, "mistral_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                data = r.json()
            models = [
                {
                    "id": m["id"],
                    "name": m.get("name", m["id"]),
                    "context_length": 0,
                    "supports_vision": "pixtral" in m.get("id", "").lower(),
                }
                for m in data.get("data", [])
            ]
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        return {"ok": False, "error": f"No live model list for {name!r}", "models": [], "source": "none"}

    except Exception as exc:
        return {"ok": False, "source": "error", "error": str(exc), "models": []}


_OPENROUTER_FALLBACK_MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-2-9b-it:free",
    "google/gemma-3-12b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "qwen/qwen-2-7b-instruct:free",
    "qwen/qwen3-8b:free",
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]


@app.get("/api/providers/openrouter/models")
async def api_openrouter_models() -> dict:
    """Fetch live free model list from OpenRouter — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"HTTP-Referer": "https://websearchai.local", "X-Title": "WebSearchAi"},
            )
            r.raise_for_status()
            data = r.json()

        free: list[dict] = []
        for m in data.get("data", []):
            model_id: str = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_price = str(pricing.get("prompt", "1"))
            completion_price = str(pricing.get("completion", "1"))
            is_free = model_id.endswith(":free") or (
                prompt_price in ("0", "0.0") and completion_price in ("0", "0.0")
            )
            if is_free:
                free.append({
                    "id": model_id,
                    "name": m.get("name", model_id),
                    "context_length": m.get("context_length", 0),
                    "supports_vision": any(
                        "image" in str(mod).lower()
                        for mod in m.get("architecture", {}).get("modality", "").split("+")
                    ),
                })

        free.sort(key=lambda x: x["id"])
        return {"ok": True, "source": "live", "models": free}

    except Exception as exc:
        fallback = [{"id": mid, "name": mid, "context_length": 0, "supports_vision": False}
                    for mid in _OPENROUTER_FALLBACK_MODELS]
        return {"ok": False, "source": "fallback", "error": str(exc), "models": fallback}
