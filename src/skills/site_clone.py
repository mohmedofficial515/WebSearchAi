"""Skill: crawl and clone an entire site using BFS + sitemap discovery."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..core.browser import BrowserSession
from ..utils.logger import log


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PageResult:
    url: str
    title: str
    html_path: str
    screenshot_path: str
    links_found: int
    status: str          # "ok" | "error"
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "html_path": self.html_path,
            "screenshot_path": self.screenshot_path,
            "links_found": self.links_found,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class SiteCloneResult:
    root_url: str
    out_dir: str
    pages: list[PageResult]
    total_pages: int
    sitemap_urls: list[str]
    crawled_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "root_url": self.root_url,
            "out_dir": self.out_dir,
            "total_pages": self.total_pages,
            "sitemap_urls_found": len(self.sitemap_urls),
            "pages": [p.to_dict() for p in self.pages],
            "crawled_at": self.crawled_at,
        }


# ── Pure helpers ──────────────────────────────────────────────────────────────


def _slugify(url: str) -> str:
    p = urlparse(url)
    s = (p.netloc + p.path).strip("/").replace("/", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s)[:80] or "site"


def _url_to_dirname(url: str) -> str:
    """Map a URL to a short filesystem-safe directory name."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "home"
    path = path.replace("/", "_")
    if parsed.query:
        import hashlib
        q_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:6]
        path = f"{path}__{q_hash}"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", path)[:60] or "page"


def _normalize_url(url: str) -> str:
    """Strip fragment from URL; used for deduplication."""
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _same_domain(url: str, domain: str) -> bool:
    """True when *url* belongs to *domain* (www-agnostic)."""
    netloc = urlparse(url).netloc
    bare_domain = domain.removeprefix("www.")
    bare_netloc = netloc.removeprefix("www.")
    return bare_netloc == bare_domain


def _get_links(html: str, base_url: str, base_domain: str) -> list[str]:
    """Return all unique same-domain absolute links found in *html*."""
    soup = BeautifulSoup(html, "lxml")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base_url, href)
        clean = _normalize_url(abs_url)
        parsed = urlparse(clean)
        if parsed.scheme not in ("http", "https"):
            continue
        if _same_domain(clean, base_domain):
            seen[clean] = None
    return list(seen)


def _parse_sitemap_xml(xml_text: str) -> list[str]:
    """Extract <loc> URLs from a sitemap XML string."""
    from xml.etree import ElementTree as ET
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        for elem in root.iter(f"{ns}loc"):
            if elem.text:
                urls.append(elem.text.strip())
    except ET.ParseError:
        # Fallback: regex
        urls = [m.strip() for m in re.findall(r"<loc>([^<]+)</loc>", xml_text)]
    return list(dict.fromkeys(urls))


# ── Network helpers ───────────────────────────────────────────────────────────


async def _get_sitemap_urls(client: httpx.AsyncClient, root_url: str) -> list[str]:
    """Discover and parse all sitemaps for *root_url*. Returns list of page URLs."""
    parsed = urlparse(root_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    candidates: list[str] = []

    # robots.txt may advertise sitemap location
    try:
        r = await client.get(f"{origin}/robots.txt")
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    candidates.append(line.split(":", 1)[1].strip())
    except Exception:  # noqa: BLE001
        pass

    candidates += [
        f"{origin}/sitemap.xml",
        f"{origin}/sitemap_index.xml",
        f"{origin}/sitemap",
    ]

    urls: list[str] = []
    visited_sitemaps: set[str] = set()

    for sm_url in candidates:
        if sm_url in visited_sitemaps:
            continue
        visited_sitemaps.add(sm_url)
        try:
            r = await client.get(sm_url)
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "")
            if "xml" not in ct and not sm_url.endswith((".xml", "/sitemap")):
                continue
            found = _parse_sitemap_xml(r.text)
            if not found:
                continue

            # Sitemap index? recurse one level
            xml_sub = [u for u in found if u.endswith(".xml")]
            if xml_sub and len(xml_sub) == len(found):
                for nested in xml_sub[:8]:
                    if nested in visited_sitemaps:
                        continue
                    visited_sitemaps.add(nested)
                    try:
                        nr = await client.get(nested)
                        if nr.status_code == 200:
                            urls.extend(_parse_sitemap_xml(nr.text))
                    except Exception:  # noqa: BLE001
                        pass
            else:
                urls.extend(found)
            break  # one sitemap source is enough
        except Exception:  # noqa: BLE001
            continue

    return list(dict.fromkeys(urls))


async def _crawl_page(
    client: httpx.AsyncClient,
    session: BrowserSession | None,
    url: str,
    pages_dir: Path,
    *,
    take_screenshots: bool,
) -> PageResult:
    """Fetch *url*, write HTML to disk, optionally capture screenshot."""
    dir_name = _url_to_dirname(url)
    page_dir = pages_dir / dir_name
    page_dir.mkdir(parents=True, exist_ok=True)

    html_path = page_dir / "page.html"
    screenshot_path_str = ""

    try:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
        html_path.write_text(html, encoding="utf-8")

        # Only parse HTML responses for links/title; skip XML, JSON, etc.
        content_type = resp.headers.get("content-type", "text/html")
        is_html = "html" in content_type
        title = ""
        links: list[str] = []
        if is_html:
            soup = BeautifulSoup(html, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            links = _get_links(html, url, urlparse(url).netloc)

        if take_screenshots and session:
            try:
                await session.goto(url)
                shot = await session.screenshot()
                sp = page_dir / "screenshot.png"
                sp.write_bytes(shot)
                screenshot_path_str = str(sp)
            except Exception as exc:  # noqa: BLE001
                log.warning("Screenshot failed for %s: %s", url, exc)

        return PageResult(
            url=url,
            title=title,
            html_path=str(html_path),
            screenshot_path=screenshot_path_str,
            links_found=len(links),
            status="ok",
        )

    except Exception as exc:  # noqa: BLE001
        log.warning("Crawl failed for %s: %s", url, exc)
        return PageResult(
            url=url,
            title="",
            html_path=str(html_path),
            screenshot_path="",
            links_found=0,
            status="error",
            error=str(exc),
        )


# ── Public API ────────────────────────────────────────────────────────────────


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


async def site_clone(
    url: str,
    *,
    max_pages: int = 50,
    max_depth: int = 3,
    take_screenshots: bool = False,
    headless: bool = True,
    delay_between_pages: float = 0.3,
) -> SiteCloneResult:
    """Crawl *url* with BFS and save HTML (+ optional screenshots) for every page.

    Args:
        url:                  Root URL to start crawling from.
        max_pages:            Hard cap on number of pages to crawl.
        max_depth:            BFS depth limit (0 = root page only).
        take_screenshots:     Also capture viewport screenshots via Playwright.
        headless:             Whether Playwright runs headless (only with screenshots).
        delay_between_pages:  Seconds to wait between HTTP requests.
    """
    root_url = _normalize_url(url)
    parsed_root = urlparse(root_url)
    base_domain = parsed_root.netloc

    slug = _slugify(root_url)
    out_dir = settings.output_path / "cloned_sites" / slug / "site"
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    crawled_at = time.time()
    visited: set[str] = set()
    # queue entries: (url, depth)
    queue: deque[tuple[str, int]] = deque([(root_url, 0)])
    pages: list[PageResult] = []
    sitemap_urls: list[str] = []

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers=_DEFAULT_HEADERS,
    ) as client:
        # ── Sitemap discovery ──────────────────────────────────────────────────
        sitemap_urls = await _get_sitemap_urls(client, root_url)
        log.info("Sitemap: %d URLs discovered for %s", len(sitemap_urls), base_domain)

        # Seed BFS queue with sitemap URLs at depth 0
        for su in sitemap_urls:
            norm = _normalize_url(su)
            if _same_domain(norm, base_domain) and norm not in visited:
                queue.append((norm, 0))

        # ── Optional Playwright session ────────────────────────────────────────
        browser_session: BrowserSession | None = None
        if take_screenshots:
            browser_session = BrowserSession(headless=headless)
            await browser_session.start()

        try:
            # ── BFS loop ───────────────────────────────────────────────────────
            while queue and len(pages) < max_pages:
                current_url, depth = queue.popleft()
                norm = _normalize_url(current_url)
                if norm in visited:
                    continue
                visited.add(norm)

                log.info(
                    "Crawling [%d/%d] depth=%d: %s",
                    len(pages) + 1, max_pages, depth, norm,
                )
                page_result = await _crawl_page(
                    client=client,
                    session=browser_session,
                    url=norm,
                    pages_dir=pages_dir,
                    take_screenshots=take_screenshots,
                )
                pages.append(page_result)

                if delay_between_pages > 0:
                    await asyncio.sleep(delay_between_pages)

                # Enqueue child links within depth limit
                if depth < max_depth and page_result.status == "ok":
                    try:
                        html_content = Path(page_result.html_path).read_text(
                            encoding="utf-8", errors="ignore"
                        )
                        for link in _get_links(html_content, norm, base_domain):
                            ln = _normalize_url(link)
                            if ln not in visited:
                                queue.append((ln, depth + 1))
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Link extraction failed for %s: %s", norm, exc)

        finally:
            if browser_session:
                await browser_session.stop()

    # ── Persist manifest + link graph ─────────────────────────────────────────
    result = SiteCloneResult(
        root_url=root_url,
        out_dir=str(out_dir),
        pages=pages,
        total_pages=len(pages),
        sitemap_urls=sitemap_urls,
        crawled_at=crawled_at,
    )

    (out_dir / "manifest.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Build and save link graph
    link_graph: dict[str, list[str]] = {}
    for p in pages:
        if p.status == "ok":
            try:
                html = Path(p.html_path).read_text(encoding="utf-8", errors="ignore")
                link_graph[p.url] = _get_links(html, p.url, base_domain)
            except Exception:  # noqa: BLE001
                link_graph[p.url] = []

    (out_dir / "link_graph.json").write_text(
        json.dumps(link_graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok_count = sum(1 for p in pages if p.status == "ok")
    log.info(
        "Site clone done: %d pages (%d ok) → %s",
        len(pages), ok_count, out_dir,
    )
    return result
