"""Skill: clone a single page → clean, self-contained, local-asset HTML.

Output structure (deterministic, professional):

    outputs/cloned_sites/<slug>/
        ├── index.html        ← entry point: opens offline, formatted, Tailwind+JS
        ├── media/            ← all images (PNG, JPG, SVG, WebP, ICO, GIF)
        │   ├── img_001.png
        │   └── img_002.svg
        ├── assets/
        │   ├── styles.css    ← consolidated inline CSS extracted from source
        │   └── app.js        ← consolidated inline JS (only safe/inline scripts)
        ├── raw/              ← original captured artifact, untouched (audit trail)
        │   ├── page.html
        │   └── screenshot.png
        ├── manifest.json     ← what was downloaded, what was rewritten, what was dropped
        └── README.md         ← how to use, what was replaced and why

Design principles:
  - **Self-contained**: `file://index.html` works offline. Every `src`/`href`
    pointing to a captured asset is rewritten to `./media/...` or `./assets/...`.
  - **Filtered assets**: framework bundles (Vite/Next/Webpack hashed JS) are
    NEVER downloaded — they're useless without the build chain. We keep
    images, CSS, fonts, and tiny standalone JS only.
  - **Library swaps**: known-heavy CDN libs (jQuery, GSAP, Font Awesome) are
    swapped for lightweight equivalents in the LLM prompt. The replacement
    table is exposed in the manifest so the user knows what changed.
  - **Formatted output**: HTML runs through bs4's `prettify()` before write,
    so the file is readable and diff-friendly.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from ..core.browser import BrowserSession
from ..core.prompt_loader import load_prompt
from ..llm.mistral_client import MistralClient
from ..utils.logger import log


def _rebuild_system(locale: str = "ar") -> str:
    return load_prompt("skills/clone", locale=locale)


# ── Data ──────────────────────────────────────────────────────────────────────


@dataclass
class CloneResult:
    url: str
    out_dir: str            # base output directory (contains index.html, media/, ...)
    index_html_path: str    # the cleaned, self-contained entry point
    raw_dir: str            # untouched capture for audit
    media_count: int
    css_count: int
    js_count: int
    dropped_assets: list[str] = field(default_factory=list)  # URLs we deliberately skipped
    library_swaps: dict[str, str] = field(default_factory=dict)  # {orig: replacement}


# ── Asset classification ─────────────────────────────────────────────────────

# Image extensions go into media/. SVGs are images here; if they're really
# icons inlined as <svg>, they're handled by the HTML rewrite path instead.
_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".avif", ".bmp"}

# Font extensions — kept in media/ for simplicity (they're referenced from CSS).
_FONT_EXTS = {".woff", ".woff2", ".ttf", ".otf", ".eot"}

# Stylesheets we'd consider keeping (but only if small + standalone).
_CSS_EXTS = {".css"}

# Pattern matching Vite/Webpack/Next/Rollup output: hashed bundles. They
# look like `app-V_fkYDLd.js`, `client-qyRSZoVl.js`, `chunk-abc12345.js`.
# These never work standalone — they expect a build runtime + import map.
#
# Stricter than a length-based heuristic because plain filenames like
# `script.js`, `analytics.js`, `main.js` are also 6+ chars but ARE standalone.
# We require either:
#   (a) a `-<hash>` suffix where the hash contains both letters and digits
#       (typical content-hash shape — Vite/Webpack/Rollup signature), OR
#   (b) a known framework filename like `chunk-…`, `_buildManifest`, `polyfills-…`.
_BUNDLE_RE = re.compile(
    r"""
    (?:                                                # (a) -<hash> suffix.  Content hashes have
      -                                                # high entropy: mixed-case letters OR
      (?=[A-Za-z0-9_-]*                                # letters+digits OR letters+underscore.
         (?:                                           # Plain words like 'analytics' or 'application'
           (?:[a-z][A-Z]|[A-Z][a-z])                   # are 8+ chars but uniform case so they're
           |[0-9]                                      # excluded.
           |_
         )
      )
      [A-Za-z0-9_-]{8,}
      \.(?:js|mjs|cjs)$
    )
    |
    (?:                                                # (b) known framework filenames
      [/.\-_]
      (?:chunk-|runtime-|polyfills-|webpack-|_app-|_buildManifest|_ssgManifest|_middlewareManifest|_clientReferenceManifest)
      [A-Za-z0-9_-]*
      \.(?:js|mjs|cjs)$
    )
    """,
    re.VERBOSE,
)

# Known heavy CDN libraries we deliberately replace with lighter equivalents
# in the rebuilt HTML. The LLM prompt receives this table.
_LIBRARY_REPLACEMENTS = {
    "jquery": (
        "vanilla DOM API (document.querySelector / addEventListener)",
        "jQuery is 90 KB for what is ~10 lines of modern vanilla JS.",
    ),
    "bootstrap": (
        "Tailwind CSS utility classes",
        "Bootstrap conflicts with Tailwind utility-first approach.",
    ),
    "font-awesome": (
        "Heroicons / Lucide inline SVGs",
        "Font Awesome ships hundreds of unused glyphs as a font file.",
    ),
    "fontawesome": (
        "Heroicons / Lucide inline SVGs",
        "Font Awesome ships hundreds of unused glyphs as a font file.",
    ),
    "gsap": (
        "CSS transitions / @keyframes",
        "GSAP is overkill for typical entrance/hover effects.",
    ),
    "lodash": (
        "ES2020 native methods (Array.flat, Object.fromEntries, etc.)",
        "Modern JS has parity with most lodash helpers.",
    ),
    "moment": (
        "Intl.DateTimeFormat / Intl.RelativeTimeFormat",
        "moment.js is in maintenance mode; Intl APIs are native.",
    ),
}


def _is_framework_bundle(url: str) -> bool:
    """True when the URL looks like a build-tool bundle that won't work standalone."""
    path = urlparse(url).path
    if not path.endswith((".js", ".mjs", ".cjs")):
        return False
    return bool(_BUNDLE_RE.search(path))


def _detect_library(url: str) -> str | None:
    """Return the replacement-table key if `url` matches a known heavy lib, else None."""
    low = url.lower()
    for key in _LIBRARY_REPLACEMENTS:
        if key in low:
            return key
    return None


def _classify_asset(url: str) -> str:
    """Return one of: 'media' | 'font' | 'css' | 'js' | 'bundle' | 'lib' | 'other'.

    Only 'media', 'font', and 'css' get downloaded. 'bundle' and 'lib' are
    deliberately dropped. 'js' (small inline-ish scripts) and 'other' fall
    through to the dropped list with a note.
    """
    if _detect_library(url):
        return "lib"
    if _is_framework_bundle(url):
        return "bundle"
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in _MEDIA_EXTS:
        return "media"
    if ext in _FONT_EXTS:
        return "font"
    if ext in _CSS_EXTS:
        return "css"
    if ext in {".js", ".mjs"}:
        return "js"
    return "other"


# ── Filename helpers ─────────────────────────────────────────────────────────


def _slugify(url: str) -> str:
    p = urlparse(url)
    s = (p.netloc + p.path).strip("/").replace("/", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s)[:80] or "site"


def _safe_filename(url: str, index: int, fallback_ext: str) -> str:
    """Build a short, deterministic, collision-free filename for an asset.

    Prefer the original basename when it's readable; fall back to a numbered
    name when it's a content-hash like `app-V_fkYDLd.js`.
    """
    path = Path(urlparse(url).path)
    stem = path.stem or f"asset_{index:03d}"
    ext = path.suffix or fallback_ext
    # If the basename is mostly a content hash, use a numbered name instead.
    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", stem) and not stem.isalpha():
        return f"img_{index:03d}{ext}"
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)[:40]
    return f"{clean}_{index:03d}{ext}"


# ── Capture: original HTML + screenshot + assets ─────────────────────────────


async def _capture_source(url: str, raw_dir: Path) -> tuple[str, bytes]:
    """Open the page in patchright, write raw HTML + screenshot."""
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
    return html, screenshot


async def _download_assets(
    soup: BeautifulSoup,
    base_url: str,
    media_dir: Path,
    assets_dir: Path,
    *,
    max_assets: int,
) -> dict[str, Any]:
    """Download images/CSS/fonts in parallel. Build URL→local-path map.

    Returns:
        {
          "url_map": {orig_url: local_relative_path, …},
          "media_count": int,
          "css_count": int,
          "dropped": [{"url": str, "reason": str}, …],
          "library_swaps": {orig_url: replacement_note, …},
        }
    """
    # Collect candidate URLs and tag each with its source attribute.
    candidates: list[tuple[str, str]] = []  # (abs_url, source_tag_info)
    for tag, attr in (
        ("link", "href"),
        ("script", "src"),
        ("img", "src"),
        ("img", "srcset"),  # split below
        ("source", "src"),
        ("source", "srcset"),
        ("video", "src"),
        ("audio", "src"),
    ):
        for el in soup.find_all(tag):
            v = el.get(attr)
            if not v:
                continue
            # srcset is `url1 1x, url2 2x` — pull each URL separately.
            if attr == "srcset":
                for piece in str(v).split(","):
                    u = piece.strip().split(" ", 1)[0]
                    if u:
                        candidates.append((urljoin(base_url, u), f"{tag}@srcset"))
            else:
                candidates.append((urljoin(base_url, str(v)), f"{tag}@{attr}"))

    # Dedupe preserving order.
    seen: dict[str, str] = {}
    for url, src in candidates:
        if url not in seen:
            seen[url] = src
    candidates_unique = list(seen.items())[:max_assets]

    url_map: dict[str, str] = {}
    dropped: list[dict[str, str]] = []
    library_swaps: dict[str, str] = {}
    media_index = 0
    css_index = 0

    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; WebSearchAi-Cloner/1.0)"},
    ) as client:

        async def _fetch_one(url: str) -> tuple[str, bytes | None, int]:
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    return url, None, r.status_code
                return url, r.content, 200
            except Exception as exc:  # noqa: BLE001
                log.debug(f"asset fetch failed {url}: {exc}")
                return url, None, 0

        # Classify first so we only network-hit assets we'd actually keep.
        keep: list[str] = []
        for url, _src in candidates_unique:
            kind = _classify_asset(url)
            if kind == "lib":
                lib_key = _detect_library(url) or "?"
                replacement, reason = _LIBRARY_REPLACEMENTS[lib_key]
                library_swaps[url] = f"{lib_key} → {replacement} ({reason})"
                dropped.append({"url": url, "reason": f"library swap: {lib_key}"})
                continue
            if kind == "bundle":
                dropped.append({"url": url, "reason": "framework bundle (Vite/Webpack-hashed JS) — useless standalone"})
                continue
            if kind in ("js", "other"):
                dropped.append({"url": url, "reason": f"skipped {kind} (only media/css/font are downloaded)"})
                continue
            keep.append(url)

        # Parallel-fetch the kept ones.
        results = await asyncio.gather(*[_fetch_one(u) for u in keep])

        for url, body, status in results:
            if body is None:
                dropped.append({"url": url, "reason": f"HTTP {status}"})
                continue
            kind = _classify_asset(url)
            if kind in ("media", "font"):
                media_index += 1
                ext = Path(urlparse(url).path).suffix.lower() or ".bin"
                if kind == "font":
                    fname = _safe_filename(url, media_index, ext)
                else:
                    fname = _safe_filename(url, media_index, ext)
                (media_dir / fname).write_bytes(body)
                url_map[url] = f"./media/{fname}"
            elif kind == "css":
                css_index += 1
                fname = f"vendor_{css_index:03d}.css"
                (assets_dir / fname).write_bytes(body)
                url_map[url] = f"./assets/{fname}"

    return {
        "url_map": url_map,
        "media_count": media_index,
        "css_count": css_index,
        "dropped": dropped,
        "library_swaps": library_swaps,
    }


# ── HTML post-processing ─────────────────────────────────────────────────────


def _extract_inline_css_js(soup: BeautifulSoup, assets_dir: Path) -> tuple[int, int]:
    """Pull every <style> block into assets/styles.css and every safe inline
    <script> into assets/app.js. Returns (css_count, js_count) written.

    "Safe" inline scripts = no `type="module"` (those need import maps),
    no `src` (those are already external), no Next.js `__NEXT_DATA__` blob.
    """
    css_chunks: list[str] = []
    js_chunks: list[str] = []
    for style in soup.find_all("style"):
        txt = style.string or style.get_text() or ""
        if txt.strip():
            css_chunks.append(txt.strip())

    for script in soup.find_all("script"):
        if script.get("src"):
            continue
        if script.get("type") == "application/json":
            continue  # __NEXT_DATA__, JSON-LD, etc.
        if script.get("type") and script.get("type") not in ("text/javascript", "module"):
            continue
        txt = script.string or script.get_text() or ""
        if txt.strip() and len(txt) < 50_000:  # cap; bigger = framework runtime
            js_chunks.append(txt.strip())

    css_written = 0
    js_written = 0
    if css_chunks:
        (assets_dir / "styles.css").write_text("\n\n".join(css_chunks), encoding="utf-8")
        css_written = 1
    if js_chunks:
        (assets_dir / "app.js").write_text("\n\n".join(js_chunks), encoding="utf-8")
        js_written = 1
    return css_written, js_written


def _rewrite_asset_urls(html: str, url_map: dict[str, str]) -> str:
    """Replace every `src`/`href` in `html` that matches a captured asset
    with its local relative path. Operates on absolute and relative forms.
    """
    if not url_map:
        return html

    # Build a lookup that tolerates both the original absolute URL AND any
    # relative forms the LLM might have emitted (e.g. `/img/foo.png` when
    # the absolute was `https://site.com/img/foo.png`).
    relmap: dict[str, str] = {}
    for orig, local in url_map.items():
        relmap[orig] = local
        # Also map the path-only variant.
        path_only = urlparse(orig).path
        if path_only:
            relmap[path_only] = local
        # And the //host/path protocol-relative form.
        netloc = urlparse(orig).netloc
        if netloc:
            relmap[f"//{netloc}{path_only}"] = local

    # Sort longest-first so we replace `https://x.com/a/b.png` before `/a/b.png`.
    keys = sorted(relmap.keys(), key=len, reverse=True)
    out = html
    for k in keys:
        if k and k in out:
            out = out.replace(k, relmap[k])
    return out


def _prettify(html: str) -> str:
    """Format HTML with bs4 for readability. Falls back to original on error."""
    try:
        soup = BeautifulSoup(html, "lxml")
        # `prettify()` preserves structure but normalizes indentation/whitespace.
        return soup.prettify(formatter="html5")
    except Exception:  # noqa: BLE001
        return html


# ── README ────────────────────────────────────────────────────────────────────


def _write_readme(
    out_dir: Path,
    url: str,
    media_count: int,
    css_count: int,
    js_count: int,
    dropped: list[dict[str, str]],
    library_swaps: dict[str, str],
) -> None:
    lines = [
        f"# Cloned: {url}",
        "",
        "## Structure",
        "",
        "- `index.html` — clean, self-contained entry point. Open with `file://` to view offline.",
        "- `media/` — all images and fonts captured from the source.",
        "- `assets/styles.css` — consolidated inline `<style>` blocks from the source.",
        "- `assets/app.js` — consolidated inline `<script>` blocks (safe ones only).",
        "- `raw/` — untouched original capture (`page.html` + `screenshot.png`) for reference.",
        "- `manifest.json` — machine-readable record of what was downloaded and dropped.",
        "",
        "## What was captured",
        "",
        f"- **{media_count}** media files (images + fonts) in `media/`",
        f"- **{css_count}** consolidated CSS file (`assets/styles.css`)" if css_count else "- No inline CSS extracted",
        f"- **{js_count}** consolidated JS file (`assets/app.js`)" if js_count else "- No inline JS extracted",
        "",
    ]

    if library_swaps:
        lines += [
            "## Library replacements",
            "",
            "These heavyweight libraries were swapped for lighter equivalents:",
            "",
        ]
        for orig, note in library_swaps.items():
            lines.append(f"- `{orig}` → {note}")
        lines.append("")

    if dropped:
        lines += [
            "## Dropped assets",
            "",
            f"{len(dropped)} assets were deliberately not downloaded.",
            "Most are framework bundles (Vite/Webpack-hashed JS) that won't work standalone.",
            "",
            "<details><summary>Full list</summary>",
            "",
        ]
        for d in dropped[:80]:
            lines.append(f"- `{d['url']}` — {d['reason']}")
        if len(dropped) > 80:
            lines.append(f"- ... and {len(dropped) - 80} more")
        lines += ["", "</details>", ""]

    lines += [
        "## Limitations",
        "",
        "- Interactive behavior that depended on framework bundles (React/Vue/Next runtime) is gone.",
        "  The page is now a static snapshot with Tailwind CDN + any safe inline JS.",
        "- The LLM-rebuilt `index.html` is best-effort. For pixel-perfect archival, use `raw/page.html`",
        "  (note: that file still references the live origin's CDN for some assets).",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ── Public API ───────────────────────────────────────────────────────────────


async def clone(url: str, *, max_assets: int = 80) -> CloneResult:
    """Clone a single page into a clean, self-contained offline-viewable directory.

    See module docstring for the output structure.
    """
    base_out = Path(settings.output_path) / "cloned_sites" / _slugify(url)
    raw_dir = base_out / "raw"
    media_dir = base_out / "media"
    assets_dir = base_out / "assets"
    for d in (raw_dir, media_dir, assets_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ── 1. Capture original ───────────────────────────────────────────────
    html, _screenshot = await _capture_source(url, raw_dir)
    soup = BeautifulSoup(html, "lxml")

    # ── 2. Download filtered assets ───────────────────────────────────────
    download_info = await _download_assets(
        soup, url, media_dir, assets_dir, max_assets=max_assets,
    )
    url_map: dict[str, str] = download_info["url_map"]
    library_swaps: dict[str, str] = download_info["library_swaps"]
    dropped: list[dict[str, str]] = download_info["dropped"]
    media_count: int = download_info["media_count"]
    vendor_css_count: int = download_info["css_count"]

    # ── 3. Extract inline CSS + safe inline JS ────────────────────────────
    inline_css, inline_js = _extract_inline_css_js(soup, assets_dir)
    css_count = vendor_css_count + inline_css
    js_count = inline_js

    # ── 4. LLM rebuild with full context (assets, swaps, structure) ───────
    body_html = str(soup.body or soup)[:80000]
    swaps_hint = "\n".join(
        f"- {orig} → {note}" for orig, note in list(library_swaps.items())[:10]
    ) or "(none)"
    media_hint = "\n".join(
        f"- {orig} → {local}" for orig, local in list(url_map.items())[:30]
    ) or "(no local assets captured)"

    llm = MistralClient()
    try:
        prompt_user = (
            f"SOURCE URL: {url}\n\n"
            f"===== LOCAL ASSET MAP (use these RELATIVE paths in the rebuilt HTML) =====\n"
            f"{media_hint}\n\n"
            f"===== LIBRARY SWAPS (do NOT include these CDN scripts; use the listed alternative) =====\n"
            f"{swaps_hint}\n\n"
            f"===== HTML BODY (source) =====\n{body_html}\n"
        )
        rebuilt_raw = await llm.chat(
            messages=[
                {"role": "system", "content": _rebuild_system()},
                {"role": "user", "content": prompt_user},
            ],
            max_tokens=8000,
            temperature=0.2,
        )
    finally:
        await llm.close()

    rebuilt = _strip_code_fence(rebuilt_raw)

    # ── 5. Rewrite any URLs the LLM emitted to point at local copies ──────
    rebuilt = _rewrite_asset_urls(rebuilt, url_map)

    # ── 6. Format for readability ─────────────────────────────────────────
    rebuilt = _prettify(rebuilt)

    index_path = base_out / "index.html"
    index_path.write_text(rebuilt, encoding="utf-8")

    # ── 7. Manifest + README ──────────────────────────────────────────────
    manifest = {
        "source_url": url,
        "out_dir": str(base_out),
        "index_html": str(index_path),
        "raw_dir": str(raw_dir),
        "media_count": media_count,
        "css_count": css_count,
        "js_count": js_count,
        "library_swaps": library_swaps,
        "dropped_count": len(dropped),
        "url_map": url_map,
        "dropped": dropped,
    }
    (base_out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _write_readme(
        base_out, url, media_count, css_count, js_count, dropped, library_swaps,
    )

    log.info(
        "clone done: %s → %d media, %d css, %d js, %d dropped",
        url, media_count, css_count, js_count, len(dropped),
    )

    return CloneResult(
        url=url,
        out_dir=str(base_out),
        index_html_path=str(index_path),
        raw_dir=str(raw_dir),
        media_count=media_count,
        css_count=css_count,
        js_count=js_count,
        dropped_assets=[d["url"] for d in dropped],
        library_swaps=library_swaps,
    )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()
