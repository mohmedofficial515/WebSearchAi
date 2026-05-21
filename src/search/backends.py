"""Search backends — parallel multi-engine dispatcher with redundancy.

Architecture (replaces the old serial fallback chain):

    ┌──────────────────────────────────────────────────────┐
    │  search(query)                                        │
    │      ↓                                                │
    │  parallel fan-out across all available engines        │
    │      ├─ tavily      (if TAVILY_API_KEY set)           │
    │      ├─ browser     (patchright → Bing SERP scrape)   │
    │      ├─ ddg_html    (browser → DuckDuckGo HTML)       │
    │      └─ ddgs        (DDGS library — last resort)      │
    │      ↓                                                │
    │  merge & dedupe results across engines                │
    │      ↓                                                │
    │  return when first engine yields results OR all done  │
    └──────────────────────────────────────────────────────┘

Why parallel instead of serial:
  - Bing's bot-detection redirect breaks the scraper ~50% of the time;
    DDG HTML is more reliable but slightly worse ranking. Running both
    in parallel and merging gives us belt-AND-suspenders coverage.
  - Tavily (when keyed) is faster than any scrape; if it returns first
    we cancel the slower scrapes.
  - The old serial chain meant a Bing failure burned 15s before we
    even *tried* DDG.

Backwards-compatible: `search_backend=browser|tavily|ddgs` still
short-circuits to that single engine; `auto` triggers the parallel
fan-out.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import quote_plus, urlparse

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


# ── Language detection (cheap, no external deps) ────────────────────────────

_ARABIC_RE = re.compile(r"[؀-ۿ]")


def _is_arabic(text: str) -> bool:
    """Return True if the query has any Arabic characters.

    Used to pick a sensible UI lang for Bing so we don't get bounced
    through Bing's lang-mismatch interstitial (which doesn't render
    `li.b_algo` — see _BING_REDIRECT_MARKERS below).
    """
    return bool(_ARABIC_RE.search(text or ""))


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


# ── DDGS library (DuckDuckGo) ───────────────────────────────────────────────

async def _ddgs_search(query: str, max_results: int) -> list[SearchResult]:
    from ddgs import DDGS

    def _sync_call() -> list[dict]:
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


# ── Browser SERP scrapes (Bing + DDG HTML) ─────────────────────────────────

# JS extractor for Bing's organic results. `li.b_algo` is the SERP item
# class Bing has used for years; the title is in `h2 > a`, the snippet
# in `.b_caption p` (or `.b_lineclamp2` on the newer card variants).
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

# DuckDuckGo HTML (no-JS) SERP extractor. The HTML endpoint
# (`html.duckduckgo.com/html`) returns a static page — no
# JS-rendering needed, no bot-detection interstitial.
_DDG_HTML_EXTRACT_JS = """
(maxN) => Array.from(document.querySelectorAll('div.result, div.web-result')).slice(0, maxN).map(el => {
    const a = el.querySelector('a.result__a, a.result__url, h2 a');
    const cap = el.querySelector('.result__snippet, .result__body, a.result__snippet');
    let url = a?.href || '';
    // DDG wraps outbound URLs in a redirect — unwrap if present.
    try {
        const u = new URL(url);
        const real = u.searchParams.get('uddg') || u.searchParams.get('u');
        if (real) url = decodeURIComponent(real);
    } catch (_) {}
    return {
        title: (a?.innerText || '').trim(),
        url: url,
        snippet: (cap?.innerText || '').trim(),
    };
}).filter(r => r.url && r.url.startsWith('http'))
"""

# When Bing rewrites to its consent/disambiguation page, the URL gets
# decorated with `rdr=1` / `rdrig=...` AND the page won't contain
# `li.b_algo`. We detect this fast (3 s probe) instead of waiting the
# full 15 s timeout, then bail out and let the parallel siblings win.
_BING_REDIRECT_MARKERS = ("rdr=1", "/ck/a?", "consent.")


# Two browser sessions can run concurrently (one for Bing, one for DDG).
# We cap at 2 because each persistent context holds a Chrome process —
# more than that thrashes the machine.
_BROWSER_SEMAPHORE = asyncio.Semaphore(2)


def _build_bing_url(query: str) -> str:
    """Construct a Bing SERP URL that matches the query's language.

    Forcing `setlang=en` on an Arabic query was the dominant source of
    the bot-detection redirect interstitial we used to hit on every
    Arabic search. We now match `setlang` to the script of the query.
    """
    q = quote_plus(query)
    lang = "ar" if _is_arabic(query) else "en"
    cc = "EG" if lang == "ar" else "US"
    return f"https://www.bing.com/search?q={q}&setlang={lang}&cc={cc}"


def _build_ddg_html_url(query: str) -> str:
    """DDG HTML endpoint — static page, no JS, no bot wall."""
    return f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"


async def _scrape_serp(
    max_results: int,
    *,
    url: str,
    extractor_js: str,
    result_selector: str,
    source: str,
    redirect_markers: tuple[str, ...] = (),
    wait_ms: int = 8_000,
) -> list[SearchResult]:
    """Generic SERP-scrape worker for browser-driven engines.

    `redirect_markers` lets the caller declare URL fragments that
    mean "the engine threw us into an interstitial" — when detected,
    we abort fast instead of waiting `wait_ms` for a selector that
    will never appear.
    """
    from ..core.browser import BrowserSession

    async with _BROWSER_SEMAPHORE:
        search_dir = settings.output_path / f"search_profile_{source}"
        sess = BrowserSession(headless=True, user_data_dir=search_dir)
        try:
            await sess.start()
            await sess.goto(url)

            # Quick redirect-detection: if the engine bounced us to an
            # interstitial we abort in ~1 s instead of burning `wait_ms`.
            if redirect_markers:
                try:
                    landed = await sess.url()
                    if any(m in landed for m in redirect_markers):
                        log.debug(f"   ↳ {source}: detected redirect interstitial ({landed[:80]}) — aborting")
                        return []
                except Exception:
                    pass

            try:
                await sess.wait_for(result_selector, timeout=wait_ms)
            except Exception as exc:
                # Selector never appeared — could be interstitial,
                # zero results, or layout change. Treat as zero results
                # and let parallel siblings win.
                log.debug(f"   ↳ {source}: {result_selector} never appeared ({type(exc).__name__})")
                return []

            raw = await sess.eval_js(f"({extractor_js})({max_results})")
        finally:
            await sess.stop()

    items = raw if isinstance(raw, list) else []
    out: list[SearchResult] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url_ = str(it.get("url") or "").strip()
        if not url_ or not url_.startswith(("http://", "https://")):
            continue
        # Don't keep links back to the engine itself.
        host = (urlparse(url_).hostname or "").lower()
        if "bing.com" in host or "duckduckgo.com" in host:
            continue
        out.append(
            SearchResult(
                title=str(it.get("title") or "").strip(),
                url=url_,
                snippet=str(it.get("snippet") or "").strip()[:500],
                source=source,
            )
        )
    return out


async def _browser_search(query: str, max_results: int) -> list[SearchResult]:
    """Bing SERP via patchright."""
    return await _scrape_serp(
        max_results,
        url=_build_bing_url(query),
        extractor_js=_BING_EXTRACT_JS,
        result_selector="li.b_algo",
        source="bing",
        redirect_markers=_BING_REDIRECT_MARKERS,
        wait_ms=8_000,
    )


async def _ddg_html_search(query: str, max_results: int) -> list[SearchResult]:
    """DuckDuckGo HTML (no-JS) SERP via patchright."""
    return await _scrape_serp(
        max_results,
        url=_build_ddg_html_url(query),
        extractor_js=_DDG_HTML_EXTRACT_JS,
        result_selector="div.result, div.web-result",
        source="ddg_html",
        wait_ms=8_000,
    )


# ── Dispatcher ───────────────────────────────────────────────────────────────

# Module-level health surface. Each entry is "<backend>: <last error str>"
# or absent when the backend last succeeded.
last_errors: dict[str, str] = {}


def _dedupe_merge(batches: list[list[SearchResult]]) -> list[SearchResult]:
    """Merge results from multiple engines, dedupe by normalized URL,
    preserve the order of the engine that surfaced each URL first."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for batch in batches:
        for r in batch:
            try:
                p = urlparse(r.url)
                key = ((p.hostname or "").lower().lstrip("www.") + (p.path or "/").rstrip("/")) or r.url.lower()
            except Exception:
                key = r.url.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


async def _run_single(name: str, coro_fn, query: str, n: int) -> tuple[str, list[SearchResult] | None, Exception | None]:
    """Run one engine with full exception isolation.

    Catches `Exception` (NOT BaseException) so KeyboardInterrupt,
    SystemExit, and asyncio.CancelledError still propagate, but
    every realistic engine failure (Playwright TimeoutError, HTTP
    errors, JSON parse errors, ImportError when SDK missing) is
    swallowed so a single broken sibling can't kill the fan-out.
    """
    log.info(f"🔎 [{name}] {query[:80]}")
    try:
        results = await coro_fn(query, n)
        if results:
            log.info(f"   ↳ {name}: {len(results)} results")
            last_errors.pop(name, None)
            return name, results, None
        last_errors[name] = "0 results"
        return name, [], None
    except Exception as exc:  # noqa: BLE001 — engine failures must NEVER kill the fan-out
        last_errors[name] = f"{type(exc).__name__}: {str(exc)[:120]}"
        log.warning(f"   ↳ {name} failed: {type(exc).__name__}: {str(exc)[:120]}")
        return name, None, exc


async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Run the query through one or many engines in parallel.

    Strategy:
        - settings.search_backend == "auto": fan out across all available
          engines in parallel, merge + dedupe. The richest combined set wins.
        - settings.search_backend == <name>: only that engine.
    """
    n = max_results or settings.search_max_results
    pref = (settings.search_backend or "auto").lower()

    # Build the engine roster. Each entry is (name, async-callable).
    engines: list[tuple[str, Any]] = []
    if pref == "tavily":
        if settings.tavily_api_key:
            engines.append(("tavily", _tavily_search))
    elif pref == "ddgs":
        engines.append(("ddgs", _ddgs_search))
    elif pref == "browser":
        engines.append(("bing", _browser_search))
    elif pref == "ddg_html":
        engines.append(("ddg_html", _ddg_html_search))
    else:  # auto — parallel fan-out
        if settings.tavily_api_key:
            engines.append(("tavily", _tavily_search))
        engines.append(("bing", _browser_search))
        engines.append(("ddg_html", _ddg_html_search))
        # ddgs library is rate-limited; keep it as a last-resort sibling
        # rather than the primary fallback.
        engines.append(("ddgs", _ddgs_search))

    if not engines:
        raise SearchError("No search engines configured")

    tasks = [
        asyncio.create_task(_run_single(name, fn, query, n))
        for name, fn in engines
    ]
    results_per_engine: list[list[SearchResult]] = []
    errors: list[tuple[str, Exception]] = []
    try:
        for done in asyncio.as_completed(tasks):
            name, results, err = await done
            if results:
                results_per_engine.append(results)
            elif err is not None:
                errors.append((name, err))
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    if not results_per_engine:
        err_summary = "; ".join(f"{n}={e!s:.60}" for n, e in errors) or "all returned 0 results"
        raise SearchError(f"All engines failed: {err_summary}")

    merged = _dedupe_merge(results_per_engine)
    log.info(f"   ↳ merged {sum(len(b) for b in results_per_engine)} → {len(merged)} unique results")
    return merged[: max(n, len(merged))]
