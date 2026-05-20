"""FastAPI app factory.

This module is intentionally small. It wires:
  - the Windows event-loop policy (so Playwright can spawn Chrome via subprocess)
  - the static mounts (`/static`, `/chat`, `/artifacts`)
  - every router defined under `src/api/routes/`

Pydantic request bodies and the `dispatch_skill_intent` helper are
re-exported below so older imports (`from src.api.main import RunBody`)
keep working without modification.
"""

from __future__ import annotations

import asyncio
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
    except Exception:  # noqa: BLE001 — any existing policy wins; do not fight it
        pass

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import settings
from .auth import router as auth_router
from .routes.archive import router as archive_router
from .routes.artifacts import router as artifacts_router
from .routes.chat import router as chat_router
from .routes.continuation import router as continuation_router
from .routes.costs import router as costs_router
from .routes.health import router as health_router
from .routes.intent import router as intent_router
from .routes.library import router as library_router
from .routes.memory import router as memory_router
from .routes.pipelines import router as pipelines_router
from .routes.plugins import router as plugins_router
from .routes.providers import router as providers_router
from .routes.skills import router as skills_router
from .routes.tasks import router as tasks_router
from .routes.uploads import router as uploads_router
from .routes.visual_test import router as visual_test_router
from .routes.websocket import router as websocket_router

# ── Backwards-compatible re-exports ───────────────────────────────────────────
# Tests + other modules historically imported these names directly from
# `src.api.main`. We keep that import surface stable while the actual
# implementations live in the route modules they belong to.
from .routes.models import (  # noqa: F401 — re-exported public API
    ArchiveCheckBody,
    CloneBody,
    DesignTokensBody,
    ExploreBody,
    FindComponentsBody,
    GoogleSearchBody,
    LinkedInBody,
    LoginBody,
    RunBody,
    SignupBody,
    SiteCloneBody,
    TempSignupBody,
    VisualBaselineBody,
    VisualCompareBody,
    YouTubeSearchBody,
)
from .routes.skills import dispatch_skill_intent  # noqa: F401 — used by routes/chat.py

# Legacy alias — old code reads the private name.
_dispatch_skill_intent = dispatch_skill_intent


__all__ = [
    "app",
    "dispatch_skill_intent",
    "_dispatch_skill_intent",
    # Pydantic bodies — re-exported for back-compat with tests / external callers
    "ArchiveCheckBody",
    "CloneBody",
    "DesignTokensBody",
    "ExploreBody",
    "FindComponentsBody",
    "GoogleSearchBody",
    "LinkedInBody",
    "LoginBody",
    "RunBody",
    "SignupBody",
    "SiteCloneBody",
    "TempSignupBody",
    "VisualBaselineBody",
    "VisualCompareBody",
    "YouTubeSearchBody",
]


ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"


app = FastAPI(
    title="WebSearchAi",
    version="0.1.0",
    description="Professional AI-driven browser automation",
)

# ── Routers ─────────────────────────────────────────────────────────────────
# Order matters only when prefixes overlap. We keep auth first so its
# dependencies run before any other route that depends on it later.
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(intent_router)
app.include_router(chat_router)
app.include_router(uploads_router)
app.include_router(artifacts_router)
app.include_router(continuation_router)
app.include_router(pipelines_router)
app.include_router(skills_router)
app.include_router(tasks_router)
app.include_router(library_router)
app.include_router(visual_test_router)
app.include_router(memory_router)
app.include_router(archive_router)
app.include_router(plugins_router)
app.include_router(costs_router)
app.include_router(providers_router)
app.include_router(websocket_router)


# ── Static mounts ───────────────────────────────────────────────────────────
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
