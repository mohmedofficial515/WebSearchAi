"""POST /api/intent — rule-based intent classification on every keystroke.

The chat composer calls this endpoint with a 300ms debounce so the skill
badge updates as the user types. We use the existing rule-based router
(`detect_intent`) — no LLM call here. A separate compound-check route
on submit handles the slower compound-detection branch.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.intent_router import detect_intent
from ...core.orchestrator import Orchestrator


router = APIRouter(prefix="/api", tags=["intent"])


class IntentRequest(BaseModel):
    message: str = Field(..., description="The user's free-form message.")


class IntentResponse(BaseModel):
    intent: str
    confidence: float
    missing_params: list[str] = Field(default_factory=list)
    is_compound: bool
    url: str | None = None
    params: dict = Field(default_factory=dict)


# Skills that need a URL the user must supply. If the rule-based router
# fires one of these but no URL was extracted, we surface the missing
# field so the UI can prompt for it before sending the message.
_URL_REQUIRED = {"login", "explore", "clone", "design_tokens"}
_CRED_REQUIRED = {"login": ("email", "password")}


@router.post("/intent", response_model=IntentResponse)
async def classify_intent(body: IntentRequest) -> IntentResponse:
    intent = detect_intent(body.message)
    missing: list[str] = []
    if intent.kind in _URL_REQUIRED and not intent.url:
        missing.append("url")
    for k in _CRED_REQUIRED.get(intent.kind, ()):
        if not intent.params.get(k):
            missing.append(k)

    # Compound detection is the cheap heuristic only — the slower LLM
    # compound check runs at submit time in the /api/chat route.
    orch = Orchestrator(llm=None, step_runner=_noop_runner)  # type: ignore[arg-type]
    is_compound = orch.is_compound_heuristic(body.message)

    return IntentResponse(
        intent=intent.kind,
        confidence=intent.confidence,
        missing_params=missing,
        is_compound=is_compound,
        url=intent.url,
        params=intent.params,
    )


async def _noop_runner(_skill: str, _params: dict) -> dict:
    """Step runner used only for the heuristic check — never actually invoked."""
    return {}
