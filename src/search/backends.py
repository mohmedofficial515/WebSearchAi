"""Search backends — browser-scrape primary, APIs secondary.

The default chain is:
    browser  (Playwright → Bing SERP scrape)  — always available
    tavily   (if TAVILY_API_KEY set, used first because it's faster)
    ddgs     (DuckDuckGo lite — last resort)

We default to scraping Bing's SERP with our patched browser because:
  - it requires no API key (zero-setup is part of the product promise),
  - the rest of the system already drives a real (patchright) browser
    that bypasses Bing's bot detection,
  - Tavily costs credits and DDGS is fragile (rate-limited, blocks IPs).

Tavily stays in the chain (faster + costs nothing once you have a key)
and DDGS stays as a no-key fallback if the browser can't launch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import quote_plus

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


# ── Browser SERP scrape (always available — no key needed) ───────────────────

# JS extractor for Bing's organic results. `li.b_algo` is the SERP item
# class Bing has used for years; the title is in `h2 > a`, the snippet
# in `.b_caption p` (or `.b_lineclamp2` on the newer card variants).
# We cap at `max_results` server-side instead of slicing in Python so
# we don't ship an oversized payload over the playwright bridge.
_BING_EXTRACT_JS = """
(maxN) => Array.from(document.querySelectorAll('li.b_algo')).slice(0, maxN).map(el => {
    const a = el.querySelector('h2 a');
    const cap = el.querySelector('.b_caption p') || el.querySelector('.b_lineclamp2');
    return {
        title: el.querySelector('h2')?.innerText || '',
        url: a?.href || '',
        snippet: cap?.innerText || '',
    };
}).filter(r => r.url)
"""


async def _browser_search(query: str, max_results: int) -> list[SearchResult]:
    """Scrape Bing's SERP using our patched browser session.

    Bing is the friendliest mainstream search engine for headless browsers
    — Google blocks aggressively, DDG-HTML rate-limits. patchright's
    binary-level stealth (already used everywhere else in the agent)
    sails through Bing's bot checks without extra ceremony.
    """
    # Local import — keeps this module importable in environments without
    # patchright (e.g. when running cheap unit tests that don't need the
    # browser at all). Also breaks an otherwise-circular core ↔ search
    # import.
    from ..core.browser import BrowserSession

    bing_url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=en"
    sess = BrowserSession(headless=True)
    try:
        await sess.start()
        await sess.goto(bing_url)
        # The SERP renders fast; cap to 15 s so we don't block forever
        # when Bing returns a CAPTCHA challenge instead of results.
        await sess.wait_for("li.b_algo", timeout=15_000)
        # Hand the max-count as an argument instead of f-string-injecting
        # it into the script — keeps the JS literal and avoids any
        # accidental quote escaping.
        raw = await sess.eval_js(f"({_BING_EXTRACT_JS})({max_results})")
    finally:
        await sess.stop()

    items = raw if isinstance(raw, list) else []
    out: list[SearchResult] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "").strip()
        if not url or not url.startswith(("http://", "https://")):
            continue
        out.append(
            SearchResult(
                title=str(it.get("title") or "").strip(),
                url=url,
                snippet=str(it.get("snippet") or "").strip()[:500],
                source="browser",
            )
        )
    return out


# ── Dispatcher ───────────────────────────────────────────────────────────────

# Module-level health surface. Each entry is "<backend>: <last error str>"
# or absent when the backend last succeeded. Cheap intermediate step toward
# the eventual /api/search/health endpoint.
last_errors: dict[str, str] = {}


async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Run the query through the best available backend.

    Order of preference (configurable via `settings.search_backend`):
        auto    → browser (always) → tavily (if key) → ddgs (last resort)
        browser → browser only
        tavily  → Tavily only
        ddgs    → DDGS only
    """
    n = max_results or settings.search_max_results
    pref = (settings.search_backend or "auto").lower()

    chain: list[str]
    if pref == "browser":
        chain = ["browser"]
    elif pref == "tavily":
        chain = ["tavily"]
    elif pref == "ddgs":
        chain = ["ddgs"]
    else:  # auto — browser first (always available), tavily if keyed, ddgs as final fallback
        chain = ["browser"]
        if settings.tavily_api_key:
            chain.insert(0, "tavily")  # API hit is faster when configured
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
            elif backend == "browser":
                log.info(f"🔎 Browser (Bing) search: {query[:80]}")
                results = await _browser_search(query, n)
            else:
                continue

            if results:
                log.info(f"   ↳ {len(results)} results from {backend}")
                last_errors.pop(backend, None)
                return results
            log.warning(f"   ↳ {backend} returned 0 results, trying next backend")
            last_errors[backend] = "returned 0 results"
        except (OSError, asyncio.TimeoutError, RuntimeError, ValueError, ImportError) as exc:
            # OSError covers network failures (DNS, refused, reset); TimeoutError
            # covers `wait_for_selector` deadlines; RuntimeError catches Playwright's
            # generic surface (page closed, target detached); ValueError/ImportError
            # catch JSON-shape and missing-SDK problems. We deliberately do NOT
            # catch arbitrary Exception: real bugs (KeyError in our own code,
            # AssertionError, etc.) should bubble up so we see them in logs.
            last_err = exc
            last_errors[backend] = f"{type(exc).__name__}: {exc}"
            log.exception(f"   ↳ {backend} backend failed")

    raise SearchError(
        f"All search backends failed (tried {chain}). Last error: {last_err}"
    )
