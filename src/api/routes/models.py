"""Pydantic request bodies shared across the HTTP routers.

Keeping these in one place (instead of next to each route) keeps the
route modules slim and lets `src/api/main.py` re-export them so older
imports such as `from src.api.main import RunBody` keep working.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunBody(BaseModel):
    goal: str = Field("", description="Natural-language goal for the agent")
    parallel_goals: list[str] = Field(
        default_factory=list, description="Run multiple goals concurrently"
    )
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


class GoogleSearchBody(BaseModel):
    query: str
    max_results: int = 10


class YouTubeSearchBody(BaseModel):
    query: str
    max_results: int = 10


class LinkedInBody(BaseModel):
    url: str


class ArchiveCheckBody(BaseModel):
    goal: str = Field(..., description="The new goal the user is about to run.")
    threshold: float = Field(0.55, ge=0.0, le=1.0)


__all__ = [
    "RunBody",
    "SignupBody",
    "LoginBody",
    "ExploreBody",
    "CloneBody",
    "SiteCloneBody",
    "TempSignupBody",
    "FindComponentsBody",
    "DesignTokensBody",
    "VisualBaselineBody",
    "VisualCompareBody",
    "GoogleSearchBody",
    "YouTubeSearchBody",
    "LinkedInBody",
    "ArchiveCheckBody",
]
