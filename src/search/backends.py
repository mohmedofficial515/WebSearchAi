"""Search backends — API-first.

We hit a real search API (Tavily) when a key is configured, and fall
back to DDGS (DuckDuckGo's lite JSON endpoint, no key required). This
sidesteps the Bing / Google CAPTCHA wall entirely for the most common
agent task: "find me URLs to visit".

The browser is only used to *visit* the URLs the search returns —
that's a much weaker bot signal than typing a query into a search box.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from typing import Any

from ..config import settings
from ..utils.logger import log


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str  # which backend produced this — for debugging / logs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SearchError(RuntimeError):
    """All configured backends failed."""


# ── Tavily ───────────────────────────────────────────────────────────────────

async def _tavily_search(query: str, max_results: int) -> list[SearchResult]:
    from tavily import TavilyClient

    def _sync_call() -> dict:
        client = TavilyClient(api_key=settings.tavily_api_key)
        return client.search(
            query=query,
            search_depth="basic",  # "advanced" costs more credits
            max_results=max_results,
            include_raw_content=False,
        )

    # tavily-python is sync; run it in a thread so we don't block the loop.
    raw = await asyncio.to_thread(_sync_call)
    items = raw.get("results", []) or []
    return [
        SearchResult(
            title=str(it.get("title") or "").strip(),
            url=str(it.get("url") or "").strip(),
            snippet=str(it.get("content") or "").strip()[:500],
            source="tavily",
        )
        for it in items
        if it.get("url")
    ]


# ── DDGS (DuckDuckGo HTML) ───────────────────────────────────────────────────

async def _ddgs_search(query: str, max_results: int) -> list[SearchResult]:
    from ddgs import DDGS

    def _sync_call() -> list[dict]:
        # `ddgs` is sync. region="wt-wt" = worldwide, safesearch off so
        # we get neutral results instead of the kids-mode set.
        with DDGS() as d:
            return list(
                d.text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=max_results,
                )
            )

    items = await asyncio.to_thread(_sync_call)
    out: list[SearchResult] = []
    for it in items or []:
        # ddgs returns either "href"/"body" (older) or "url"/"body" (newer)
        url = it.get("href") or it.get("url") or ""
        if not url:
            continue
        out.append(
            SearchResult(
                title=str(it.get("title") or "").strip(),
                url=str(url).strip(),
                snippet=str(it.get("body") or "").strip()[:500],
                source="ddgs",
            )
        )
    return out


# ── Dispatcher ───────────────────────────────────────────────────────────────

async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Run the query through the best available backend.

    Order of preference (configurable via `settings.search_backend`):
        auto    → Tavily (if key) → DDGS
        tavily  → Tavily only
        ddgs    → DDGS only
        browser → raise SearchError — caller scrapes a search engine page
    """
    n = max_results or settings.search_max_results
    pref = (settings.search_backend or "auto").lower()

    chain: list[str]
    if pref == "tavily":
        chain = ["tavily"]
    elif pref == "ddgs":
        chain = ["ddgs"]
    elif pref == "browser":
        raise SearchError("search_backend=browser — agent should scrape directly")
    else:  # auto
        chain = []
        if settings.tavily_api_key:
            chain.append("tavily")
        chain.append("ddgs")

    last_err: Exception | None = None
    for backend in chain:
        try:
            if backend == "tavily":
                if not settings.tavily_api_key:
                    continue
                log.info(f"🔎 Tavily search: {query[:80]}")
                results = await _tavily_search(query, n)
            elif backend == "ddgs":
                log.info(f"🔎 DDGS search: {query[:80]}")
                results = await _ddgs_search(query, n)
            else:
                continue

            if results:
                log.info(f"   ↳ {len(results)} results from {backend}")
                return results
            log.warning(f"   ↳ {backend} returned 0 results, trying next backend")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log.warning(f"   ↳ {backend} failed: {exc}")

    raise SearchError(
        f"All search backends failed (tried {chain}). Last error: {last_err}"
    )
