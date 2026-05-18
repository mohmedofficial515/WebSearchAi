"""Pre-baked deterministic skills — zero LLM calls, pure Playwright flows.

Each skill drives the browser with hardcoded steps so they never consume API
tokens.  Results are automatically saved to long-term memory.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..core.browser import BrowserSession
from ..utils.logger import log


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    query: str
    results: list[dict[str, str]]
    source: str
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "source": self.source,
            "total": self.total,
            "results": self.results,
        }


@dataclass
class YouTubeResult:
    query: str
    videos: list[dict[str, str]]
    total: int = 0

    def to_dict(self) -> dict:
        return {"query": self.query, "total": self.total, "videos": self.videos}


@dataclass
class LinkedInProfile:
    url: str
    name: str = ""
    headline: str = ""
    location: str = ""
    about: str = ""
    experience: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    connections: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "name": self.name,
            "headline": self.headline,
            "location": self.location,
            "about": self.about,
            "experience": self.experience,
            "education": self.education,
            "skills": self.skills,
            "connections": self.connections,
            "error": self.error,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _new_session() -> BrowserSession:
    s = BrowserSession(headless=settings.browser_headless)
    await s.start()
    return s


async def _save_to_memory(site: str, flow_type: str, data: dict) -> None:
    try:
        from ..memory import get_memory
        mem = await get_memory()
        await mem.touch_site(site)
        await mem.remember_flow(site, flow_type, data)
    except Exception as exc:
        log.debug(f"Memory save skipped ({flow_type}): {exc}")


# ── Google Search ─────────────────────────────────────────────────────────────

_GOOGLE_JS = """\
() => {
    const out = [];
    document.querySelectorAll('div.g, div[jscontroller]').forEach(el => {
        const a   = el.querySelector('a[href]');
        const h3  = el.querySelector('h3');
        const snp = el.querySelector('.VwiC3b, [data-sncf], .s3v9rd, .IsZvec');
        if (h3 && a && a.href.startsWith('http') && !a.href.includes('google.com/search')) {
            out.push({
                title:   h3.textContent.trim(),
                url:     a.href,
                snippet: snp ? snp.textContent.trim().slice(0, 300) : ''
            });
        }
    });
    return out;
}
"""


async def google_search(query: str, max_results: int = 10) -> SearchResult:
    """Search Google — deterministic, zero LLM calls."""
    session = await _new_session()
    results: list[dict[str, str]] = []
    try:
        page = session.page
        assert page
        await session.goto("https://www.google.com")
        sel = 'textarea[name="q"], input[name="q"]'
        await page.wait_for_selector(sel, timeout=8000)
        await session.type(sel.split(",")[0].strip(), query)
        await session.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(1.5)
        raw: list[dict] = await session.eval_js(_GOOGLE_JS) or []
        results = [r for r in raw if r.get("url")][:max_results]
        log.info(f"google_search '{query}' → {len(results)} results")
        await _save_to_memory(
            "https://www.google.com",
            "google_search",
            {"query": query, "result_count": len(results)},
        )
    except Exception as exc:
        log.warning(f"google_search error: {exc}")
    finally:
        await session.stop()
    return SearchResult(query=query, results=results, source="google", total=len(results))


# ── YouTube Search ────────────────────────────────────────────────────────────

_YOUTUBE_JS = """\
() => {
    const vids = [];
    document.querySelectorAll('ytd-video-renderer, ytd-compact-video-renderer').forEach(el => {
        const titleEl    = el.querySelector('#video-title, a#video-title');
        const channelEl  = el.querySelector('#channel-name a, ytd-channel-name a');
        const metaSpans  = el.querySelectorAll('#metadata-line span');
        const durationEl = el.querySelector('span.ytd-thumbnail-overlay-time-status-renderer');
        if (!titleEl) return;
        const href = titleEl.getAttribute('href') || '';
        vids.push({
            title:    titleEl.textContent.trim(),
            url:      href.startsWith('http') ? href : 'https://www.youtube.com' + href,
            channel:  channelEl  ? channelEl.textContent.trim()  : '',
            views:    metaSpans[0] ? metaSpans[0].textContent.trim() : '',
            uploaded: metaSpans[1] ? metaSpans[1].textContent.trim() : '',
            duration: durationEl ? durationEl.textContent.trim() : ''
        });
    });
    return vids;
}
"""


async def youtube_search(query: str, max_results: int = 10) -> YouTubeResult:
    """Search YouTube — deterministic, zero LLM calls."""
    session = await _new_session()
    videos: list[dict[str, str]] = []
    try:
        page = session.page
        assert page
        await session.goto("https://www.youtube.com")
        await page.wait_for_selector("input#search", timeout=10000)
        await session.type("input#search", query)
        await session.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)
        raw: list[dict] = await session.eval_js(_YOUTUBE_JS) or []
        videos = [v for v in raw if v.get("url")][:max_results]
        log.info(f"youtube_search '{query}' → {len(videos)} videos")
        await _save_to_memory(
            "https://www.youtube.com",
            "youtube_search",
            {"query": query, "result_count": len(videos)},
        )
    except Exception as exc:
        log.warning(f"youtube_search error: {exc}")
    finally:
        await session.stop()
    return YouTubeResult(query=query, videos=videos, total=len(videos))


# ── LinkedIn Profile Extractor ────────────────────────────────────────────────

_LINKEDIN_JS = """\
() => {
    const t = sel => (document.querySelector(sel) || {}).textContent?.trim() || '';
    const all = sel => Array.from(document.querySelectorAll(sel))
                           .map(e => e.textContent.trim())
                           .filter(Boolean);
    return {
        name:        t('h1.text-heading-xlarge, h1[class*="heading"]'),
        headline:    t('.text-body-medium.break-words, [class*="headline"]'),
        location:    t('.text-body-small.inline.t-black--light.break-words'),
        about:       t('section#about .full-width .visually-hidden, #about ~ .pvs-list__outer-container'),
        experience:  all('.pvs-list__item--line-separated .t-bold span[aria-hidden="true"]').slice(0, 10),
        education:   all('[id*="education"] .t-bold span[aria-hidden="true"]').slice(0, 6),
        skills:      all('[id*="skills"]  .t-bold span[aria-hidden="true"]').slice(0, 15),
        connections: t('.t-bold ~ .t-normal.t-black--light')
    };
}
"""


async def linkedin_extract_profile(profile_url: str) -> LinkedInProfile:
    """Extract structured data from a LinkedIn profile — zero LLM calls."""
    session = await _new_session()
    profile = LinkedInProfile(url=profile_url)
    try:
        page = session.page
        assert page
        await session.goto(profile_url)
        await asyncio.sleep(1)
        current = page.url
        if "linkedin.com/login" in current or "authwall" in current:
            profile.error = "LinkedIn requires login — please sign in first"
            return profile
        await asyncio.sleep(2)
        data: dict[str, Any] = await session.eval_js(_LINKEDIN_JS) or {}
        profile.name        = data.get("name", "")
        profile.headline    = data.get("headline", "")
        profile.location    = data.get("location", "")
        profile.about       = data.get("about", "")
        profile.experience  = data.get("experience", [])
        profile.education   = data.get("education", [])
        profile.skills      = data.get("skills", [])
        profile.connections = data.get("connections", "")
        log.info(f"linkedin_extract_profile → {profile.name or 'unknown'}")
        await _save_to_memory(
            "https://www.linkedin.com",
            "linkedin_extract",
            {"url": profile_url, "name": profile.name},
        )
    except Exception as exc:
        log.warning(f"linkedin_extract_profile error: {exc}")
        profile.error = str(exc)
    finally:
        await session.stop()
    return profile
