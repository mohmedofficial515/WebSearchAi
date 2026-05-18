"""Standalone brain-only harness for SearchAgent.

Runs the full search → rank → critique pipeline WITHOUT launching a
browser. Useful for iterating on the orchestration logic, prompts, and
ranking heuristics without paying the Playwright startup cost or
risking flaky page loads.

What it shows you for each test query:
  1. The diverse queries the LLM generated.
  2. Raw deduped search results from Tavily/DDGS.
  3. Heuristic score per result.
  4. LLM critique score per top-N result.
  5. Final ranked candidate list (heuristic+LLM blended).
  6. The top-K visit queue with reasoning.

Run:
    python scripts/test_search_agent.py
    python scripts/test_search_agent.py "your custom query"

Exit code: 0 if every query produced ≥ 1 candidate, 1 otherwise.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is importable when the script is run directly.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import settings
from src.core.search_agent import SearchAgent
from src.llm.providers import get_provider


_DEFAULT_QUERIES = [
    "تطبيق ديل للعقارات السعودية",
    "أخبار الذكاء الاصطناعي اليوم",
    "best Python ORM 2026",
    "كريم سعودي شروط الانضمام كسائق",
    "Anthropic Claude pricing",
    "رمز المنطقة لجدة",
]


def _hr(char: str = "─", n: int = 78) -> str:
    return char * n


async def _evaluate_query(sa: SearchAgent, goal: str) -> bool:
    print(f"\n{_hr('═')}")
    print(f"GOAL: {goal}")
    print(_hr("═"))

    events: list[tuple[str, dict]] = []

    async def _on_event(type_: str, data: dict) -> None:
        events.append((type_, data))

    research = await sa.research(goal, on_event=_on_event)

    # 1. queries
    print(f"\n[1] Generated queries ({len(research.queries)}):")
    for q in research.queries:
        print(f"    • {q}")

    # 2. raw results
    print(f"\n[2] Unique merged results: {len(research.all_results)}")
    for i, r in enumerate(research.all_results[:10]):
        host = r.get("host") or ""
        title = (r.get("title") or "")[:70]
        url = (r.get("url") or "")[:80]
        n_q = len(r.get("queries_matched") or [])
        print(f"    [{i:2d}] {host:30s}  {title}")
        print(f"         {url}  (matched {n_q} queries)")

    # 3-5. ranked candidates
    print(f"\n[3-5] Ranked candidates (top {len(research.candidates)}):")
    print(f"      {'host':30s}  {'heur':>5s}  {'llm':>5s}  {'final':>5s}  reason")
    for c in research.candidates:
        print(f"      {c.host:30s}  {c.heuristic_score:>5.2f}  {c.llm_score:>5.2f}  "
              f"{c.final_score:>5.2f}  {c.llm_reason[:60]}")

    # 6. visit queue
    print(f"\n[6] Visit queue (would visit in this order):")
    for i, c in enumerate(research.visit_queue, 1):
        print(f"    {i}. {c.url}")
        print(f"       title: {c.title[:80]}")
        print(f"       score: {c.final_score:.2f}  | reason: {c.llm_reason[:80]}")

    print(f"\nNotes: {research.notes}")
    print(f"Events emitted: {[t for t, _ in events]}")
    ok = bool(research.visit_queue)
    print(f"\nVERDICT: {'OK' if ok else 'FAIL — no candidates'}")
    return ok


async def main() -> int:
    queries = sys.argv[1:] or _DEFAULT_QUERIES
    print(f"Running SearchAgent against {len(queries)} test queries.")
    print(f"LLM provider: {settings.llm_provider}")
    print(f"Search backend: {settings.search_backend}  (tavily_key={'set' if settings.tavily_api_key else 'unset'})")

    llm = get_provider(settings)
    sa = SearchAgent(llm)

    results: list[bool] = []
    try:
        for q in queries:
            try:
                ok = await _evaluate_query(sa, q)
            except Exception as exc:  # noqa: BLE001
                print(f"\nERROR on {q!r}: {type(exc).__name__}: {exc}")
                ok = False
            results.append(ok)
    finally:
        await llm.close()

    print(f"\n{_hr('═')}")
    print(f"SUMMARY: {sum(results)}/{len(results)} queries produced candidates")
    print(_hr("═"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
