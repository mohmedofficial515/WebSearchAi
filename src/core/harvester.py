"""PageHarvester — specialized parallel page-content extractor.

A dedicated layer between the SearchAgent (which picks WHICH pages to
visit) and the Critic (which judges WHAT the page says). Replaces the
old "drive the main browser tab from URL to URL serially" pattern.

Why split this out:
  - Browser-driven visits cost ~3-5 s each (page load + render + JS).
    Visiting 6 candidates serially = 30 s before the critic even starts.
  - For 80% of search-result pages (news, wiki, blogs, government,
    docs), a plain HTTP fetch + BS4 readability extraction returns
    the same article text in ~500 ms.
  - We can fan out the HTTP fetches in parallel with `asyncio.gather`,
    so 6 fetches finish in ~1 s wall-clock.
  - The 20% of pages that are JS-only (SPAs, paywalls, anti-bot walls)
    fall back to the browser path — the existing code is already wired
    for that.

Public surface:
    harvester = PageHarvester()
    pages = await harvester.harvest_many([
        {"url": "https://...", "title": "..."},
        ...
    ])
    # pages: list[HarvestedPage] in the same order as the input
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..utils.logger import log


# Plain User-Agent — enough to clear most bot-walls, but the real
# defense against detection is the parallel browser fallback below.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

# Tags we strip before extracting text. `script`/`style` produce noise.
# `nav`/`footer`/`aside`/`form` are usually chrome around the article.
_STRIP_TAGS = {"script", "style", "nav", "footer", "aside", "form",
               "header", "noscript", "iframe", "svg"}

# A page is considered "thin" — and worth retrying via browser — when
# the extracted text is shorter than this. Real articles trivially
# exceed 600 chars; SPAs that render via JS hit ~50-200 chars of
# template-shell text.
_THIN_PAGE_THRESHOLD = 600

# How many parallel HTTP fetches at once. We're being polite-by-default
# because some hosts (Cloudflare especially) tarpit aggressive fan-out.
_DEFAULT_HTTP_CONCURRENCY = 6


@dataclass
class HarvestedPage:
    url: str
    final_url: str       # after redirects
    title: str           # from <title> or page-supplied title
    text: str            # main-content text, scrubbed
    status_code: int     # 0 if HTTP fetch never completed
    source: str          # "http" or "browser" — which path produced this
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error

    @property
    def is_thin(self) -> bool:
        """True if the extracted text is below the meaningful-content threshold."""
        return len(self.text) < _THIN_PAGE_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PageHarvester:
    """Parallel HTTP page fetcher with browser fallback for JS-only pages.

    Stateless across calls. Spawns a per-call asyncio session so we never
    leak connections between research rounds.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 12.0,
        http_concurrency: int = _DEFAULT_HTTP_CONCURRENCY,
        max_chars: int | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.http_concurrency = http_concurrency
        self.max_chars = max_chars or int(
            getattr(settings, "research_extract_chars", 14000)
        )

    # ── Public API ─────────────────────────────────────────────────────────

    async def harvest_many(
        self,
        targets: list[dict[str, Any]],
        *,
        browser_fallback: Any | None = None,
    ) -> list[HarvestedPage]:
        """Fetch many URLs in parallel via HTTP, optionally browser-fallback thin pages.

        `targets`: list of {"url": str, "title": str (optional)}.
        `browser_fallback`: an object with an async `goto(url)` and
            async `eval_js(js)` method — typically the agent's
            BrowserSession. When provided, thin/failed pages are
            retried serially through the browser.

        Returns: list[HarvestedPage] in the same order as `targets`.
        """
        if not targets:
            return []

        sem = asyncio.Semaphore(self.http_concurrency)
        async with httpx.AsyncClient(
            timeout=self.timeout_s,
            follow_redirects=True,
            # Full browser-like header set. Bare Mozilla UAs get 403'd
            # by Wikipedia, Reddit, CF-protected sites; matching the
            # full Chrome envelope (Sec-Fetch-*, Sec-Ch-Ua-*, Accept-*)
            # clears most defensive bot walls.
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ar,en-US;q=0.8,en;q=0.7",
                # No `br` — httpx only auto-decodes gzip/deflate by default,
                # and advertising brotli without supporting it makes some
                # CDNs serve us a body we can't read.
                "Accept-Encoding": "gzip, deflate",
                "Sec-Ch-Ua": '"Chromium";v="134", "Google Chrome";v="134", "Not(A:Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        ) as client:
            results = await asyncio.gather(
                *[self._http_one(client, sem, t) for t in targets],
                return_exceptions=False,  # _http_one never raises
            )

        # Browser fallback for thin/failed pages. We do this SERIALLY
        # (the browser session has one page; parallel goto's would race).
        # Most pages succeed via HTTP so this loop is usually empty.
        if browser_fallback is not None:
            for i, page in enumerate(results):
                if page.ok and not page.is_thin:
                    continue
                fallback = await self._browser_one(
                    browser_fallback, targets[i].get("url", ""), targets[i].get("title", "")
                )
                # Use the fallback only if it gave us MORE content;
                # never replace a working HTTP fetch with a worse browser one.
                if fallback.ok and len(fallback.text) > len(page.text):
                    results[i] = fallback
        return results

    # ── HTTP path ──────────────────────────────────────────────────────────

    async def _http_one(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        target: dict[str, Any],
    ) -> HarvestedPage:
        url = str(target.get("url") or "").strip()
        title_hint = str(target.get("title") or "").strip()
        if not url:
            return HarvestedPage(url="", final_url="", title=title_hint,
                                  text="", status_code=0, source="http",
                                  error="empty url")
        async with sem:
            try:
                resp = await client.get(url)
            except Exception as exc:  # noqa: BLE001
                return HarvestedPage(
                    url=url, final_url=url, title=title_hint,
                    text="", status_code=0, source="http",
                    error=f"{type(exc).__name__}: {str(exc)[:120]}",
                )

        if resp.status_code >= 400:
            return HarvestedPage(
                url=url, final_url=str(resp.url), title=title_hint,
                text="", status_code=resp.status_code, source="http",
                error=f"HTTP {resp.status_code}",
            )

        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "xml" not in ctype:
            # PDFs, JSON, images — we can't read these with bs4. Skip.
            return HarvestedPage(
                url=url, final_url=str(resp.url), title=title_hint,
                text="", status_code=resp.status_code, source="http",
                error=f"non-html content-type: {ctype[:60]}",
            )

        try:
            title, text = _extract_main_content(resp.text, fallback_title=title_hint)
        except Exception as exc:  # noqa: BLE001
            return HarvestedPage(
                url=url, final_url=str(resp.url), title=title_hint,
                text="", status_code=resp.status_code, source="http",
                error=f"extract failed: {type(exc).__name__}",
            )

        return HarvestedPage(
            url=url,
            final_url=str(resp.url),
            title=title or title_hint,
            text=text[: self.max_chars],
            status_code=resp.status_code,
            source="http",
        )

    # ── Browser-fallback path ──────────────────────────────────────────────

    async def _browser_one(
        self, session: Any, url: str, title_hint: str,
    ) -> HarvestedPage:
        """Re-fetch a thin/failed page through the real browser.

        Uses the SAME extraction logic as the HTTP path (we ask the
        page to render then bs4-extract the rendered HTML) so what the
        critic sees stays consistent across both paths.
        """
        if not url:
            return HarvestedPage(url="", final_url="", title=title_hint,
                                  text="", status_code=0, source="browser",
                                  error="empty url")
        try:
            await session.goto(url)
            html = await session.eval_js("document.documentElement.outerHTML")
        except Exception as exc:  # noqa: BLE001
            log.debug(f"browser fallback failed for {url}: {exc!s:.120}")
            return HarvestedPage(
                url=url, final_url=url, title=title_hint,
                text="", status_code=0, source="browser",
                error=f"{type(exc).__name__}: {str(exc)[:120]}",
            )

        try:
            title, text = _extract_main_content(str(html or ""), fallback_title=title_hint)
        except Exception as exc:  # noqa: BLE001
            return HarvestedPage(
                url=url, final_url=url, title=title_hint,
                text="", status_code=200, source="browser",
                error=f"extract failed: {type(exc).__name__}",
            )

        return HarvestedPage(
            url=url, final_url=url,
            title=title or title_hint,
            text=text[: self.max_chars],
            status_code=200,
            source="browser",
        )


# ── Content extraction ──────────────────────────────────────────────────────

def _extract_main_content(html: str, *, fallback_title: str = "") -> tuple[str, str]:
    """Return (title, body_text) extracted from raw HTML.

    Strategy: parse with bs4 (lxml backend for speed), strip noise tags,
    prefer `<main>` / `<article>` if present, else fall back to body text
    with run-length-encoded whitespace.
    """
    if not html:
        return fallback_title, ""
    soup = BeautifulSoup(html, "lxml")

    # Title — prefer the document <title>, then og:title, then h1.
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = str(og["content"]).strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)
    if not title:
        title = fallback_title

    # Strip noise.
    for tag in soup.find_all(list(_STRIP_TAGS)):
        tag.decompose()

    # Prefer semantic main-content containers when they exist.
    container = soup.find("main") or soup.find("article") or soup.body or soup
    text = container.get_text(" ", strip=True)
    # Collapse runs of whitespace to single spaces.
    text = " ".join(text.split())
    return title, text
