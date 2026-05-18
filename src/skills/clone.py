"""Skill: clone a website — capture assets + AI rebuild as a Next.js-style page."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..core.browser import BrowserSession
from ..llm.mistral_client import MistralClient
from ..utils.logger import log


REBUILD_SYSTEM = """You are a senior front-end engineer.

You will receive the captured HTML + CSS of a single web page. Your job is to
rebuild it as a clean, modern, responsive single-file HTML page using only:
- Tailwind CSS via <script src="https://cdn.tailwindcss.com"></script>
- Plain semantic HTML
- No external images you didn't see in the source (use the same image URLs).
- Preserve copy/text faithfully.
- Improve accessibility, responsive layout, and structure.

Output JUST the final HTML, nothing else."""


@dataclass
class CloneResult:
    url: str
    raw_dir: str
    rebuilt_html_path: str
    assets: list[str]


def _slugify(url: str) -> str:
    p = urlparse(url)
    s = (p.netloc + p.path).strip("/").replace("/", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s)[:80] or "site"


async def clone(url: str, *, max_assets: int = 60) -> CloneResult:
    base_out = Path(settings.output_path) / "cloned_sites" / _slugify(url)
    raw_dir = base_out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "assets").mkdir(exist_ok=True)

    session = BrowserSession()
    await session.start()
    try:
        await session.goto(url, wait_until="networkidle")
        html = await session.html()
        screenshot = await session.screenshot()
    finally:
        await session.stop()

    (raw_dir / "page.html").write_text(html, encoding="utf-8")
    (raw_dir / "screenshot.png").write_bytes(screenshot)

    soup = BeautifulSoup(html, "lxml")
    assets: list[str] = []

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        urls: list[str] = []
        for tag, attr in (
            ("link", "href"),
            ("script", "src"),
            ("img", "src"),
            ("source", "src"),
        ):
            for el in soup.find_all(tag):
                v = el.get(attr)
                if v:
                    urls.append(urljoin(url, v))
        urls = list(dict.fromkeys(urls))[:max_assets]

        for asset_url in urls:
            try:
                r = await client.get(asset_url)
                if r.status_code != 200:
                    continue
                name = _slugify(asset_url)
                ext = Path(urlparse(asset_url).path).suffix or ".bin"
                p = raw_dir / "assets" / f"{name}{ext}"
                p.write_bytes(r.content)
                assets.append(str(p))
            except Exception as e:  # noqa: BLE001
                log.warning(f"asset failed {asset_url}: {e}")

    css_blobs: list[str] = []
    for style in soup.find_all("style"):
        if style.string:
            css_blobs.append(style.string)
    css_text = "\n\n".join(css_blobs)[:30000]

    body_html = str(soup.body or soup)[:80000]

    llm = MistralClient()
    try:
        prompt_user = (
            f"SOURCE URL: {url}\n\n"
            f"===== INLINE CSS =====\n{css_text}\n\n"
            f"===== HTML BODY =====\n{body_html}\n"
        )
        rebuilt = await llm.chat(
            messages=[
                {"role": "system", "content": REBUILD_SYSTEM},
                {"role": "user", "content": prompt_user},
            ],
            max_tokens=8000,
            temperature=0.2,
        )
    finally:
        await llm.close()

    rebuilt_path = base_out / "rebuilt.html"
    rebuilt_path.write_text(_strip_code_fence(rebuilt), encoding="utf-8")

    (base_out / "manifest.json").write_text(
        json.dumps(
            {
                "source_url": url,
                "raw_dir": str(raw_dir),
                "rebuilt_html": str(rebuilt_path),
                "assets_count": len(assets),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return CloneResult(
        url=url,
        raw_dir=str(raw_dir),
        rebuilt_html_path=str(rebuilt_path),
        assets=assets,
    )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()
