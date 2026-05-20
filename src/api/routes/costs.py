"""LLM cost-tracker endpoints (read-only — entries are emitted from the providers)."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("")
async def api_costs_summary() -> list[dict]:
    """Daily cost summary grouped by UTC date."""
    from ...llm.costs import cost_tracker
    return cost_tracker.daily_summary()


@router.get("/entries")
async def api_costs_entries(limit: int = 100) -> list[dict]:
    """Recent raw cost entries (most recent last)."""
    from ...llm.costs import cost_tracker
    entries = cost_tracker.read_entries()
    return [e.to_dict() for e in entries[-limit:]]
