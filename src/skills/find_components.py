"""Skill: search the web for UI components and produce a real, code-bearing
project the developer can open and reuse.

What changed vs the first version:
  * Instead of just screenshotting pages and saving inline `<pre>` blocks,
    we now extract MULTIPLE variants per page using two strategies:
      A) explicit code panels — `<pre>/<code>` blocks that look like real
         component source (HTML / JSX with classes), and
      B) live demo containers — visible DOM blocks of a reasonable size
         that look like a single self-contained UI piece (cards, navbars,
         forms, etc.).
  * Each variant is converted into a clean React JSX functional component
    via the LLM (one batched JSON call also producing an Arabic
    description). The result is saved as a real `.jsx` file under
    `outputs/components/<slug>/components/<NN_variant>/Component.jsx`,
    next to a `README.md` (Arabic description), `source.html` (the raw
    HTML before LLM cleanup), and `preview.png` (cropped to the demo
    box when possible).
  * A professional `viewer.html` is generated — a self-contained SPA
    (vanilla JS + highlight.js from CDN) with a sidebar listing every
    variant grouped by source, syntax-highlighted code tabs (JSX / HTML),
    Arabic descriptions, and a copy-to-clipboard button per code block.

The output is designed so an operator can:
    open outputs/components/<slug>/viewer.html
and immediately browse all extracted components inside a clean UI — no
build step, no dependencies.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import settings
from ..core.browser import BrowserSession
from ..core.prompt_loader import load_prompt
from ..core.search_agent import RankedCandidate, SearchAgent
from ..llm.providers import get_provider
from ..reports.component_viewer import render_viewer
from ..utils.logger import log


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ComponentVariant:
    variant_id: str                 # `01_navbar_tailwindui_com`
    source_url: str
    source_host: str
    source_title: str               # page title
    name: str                       # component name (camelCased, no spaces)
    extraction_mode: str            # "code_block" | "dom_capture"
    raw_html: str                   # what we grabbed from the page
    jsx_code: str                   # cleaned-up JSX
    description_ar: str             # 2-3 Arabic sentences
    tags: list[str] = field(default_factory=list)
    preview: str = ""               # relative path to preview.png
    component_file: str = ""        # relative path to Component.jsx
    readme_file: str = ""           # relative path to README.md
    source_file: str = ""           # relative path to source.html

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComponentSearchResult:
    query: str
    out_dir: str
    viewer_html: str
    report_md: str
    variants: list[ComponentVariant] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "out_dir": self.out_dir,
            "viewer_html": self.viewer_html,
            "report_md": self.report_md,
            "n_variants": len(self.variants),
            "variants": [v.to_dict() for v in self.variants],
        }


# ── Query expansion (unchanged surface, same library hints) ──────────────────

_LIBRARY_HINTS = (
    ("tailwind", "tailwindui.com flowbite.com daisyui.com tailwindcomponents.com"),
    ("bootstrap", "getbootstrap.com bootstrapmade.com mdbootstrap.com"),
    ("material", "mui.com material.io"),
    ("ant ", "ant.design"),
    ("shadcn", "ui.shadcn.com"),
    ("chakra", "chakra-ui.com"),
)


def _query_expansion(query: str) -> list[str]:
    base = query.strip()
    qs = [base]
    low = base.lower()
    if not any(h[0] in low for h in _LIBRARY_HINTS):
        qs.extend([f"{base} tailwind", f"{base} bootstrap", f"{base} examples", f"{base} component code"])
    else:
        qs.extend([f"{base} examples", f"{base} component code", f"{base} snippet"])
    seen, out = set(), []
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k); out.append(q)
    return out[:5]


# ── In-browser extraction JS ────────────────────────────────────────────────
# Returns up to N variants from the current page. Strategy A (code blocks)
# is preferred — it gives us real component source. Strategy B (DOM capture)
# is a fallback used when a page shows a live demo without exposing source.

_EXTRACT_JS = r"""
(() => {
  const MAX_VARIANTS = 4;
  const out = { variants: [], page_title: document.title || '' };

  // ─── Strategy A — find code blocks that look like component source ───
  const codeNodes = document.querySelectorAll('pre, pre code, code[class*="language"]');
  const seenCode = new Set();
  for (const n of codeNodes) {
    if (out.variants.length >= MAX_VARIANTS) break;
    const txt = (n.innerText || '').trim();
    if (txt.length < 200 || txt.length > 6000) continue;
    if (seenCode.has(txt)) continue;
    // Heuristic: looks like component source if it has class= / className=
    // and at least one tag, OR if it has function/const/return for JSX.
    const isHtmlish = /class(Name)?\s*=/.test(txt) && /<[a-zA-Z]/.test(txt);
    const isJsxish  = /(function|const)\s+\w+\s*[\(=].*?(?:=>|\{)\s*\n?\s*return\s*\(/s.test(txt);
    if (!isHtmlish && !isJsxish) continue;
    seenCode.add(txt);
    // Try to find a screenshot anchor — the nearest preceding visible
    // element that's a reasonable size (the demo above this code block).
    let demoEl = n;
    let prev = n.closest('section, article, div, figure');
    while (prev) {
      const sib = prev.previousElementSibling;
      if (sib && sib.getBoundingClientRect().height > 40) {
        demoEl = sib; break;
      }
      prev = prev.parentElement;
      if (!prev || prev === document.body) break;
    }
    const rect = demoEl.getBoundingClientRect();
    out.variants.push({
      mode: 'code_block',
      html: txt,
      anchor_rect: { x: Math.round(rect.x), y: Math.round(rect.y + window.scrollY),
                     w: Math.round(rect.width), h: Math.round(Math.min(rect.height, 600)) },
    });
  }

  // ─── Strategy B — visible "demo" containers ───
  // Only used when we didn't find enough code blocks. We pick blocks that
  // look like single coherent UI widgets: 80-700px tall, between 200-1200px
  // wide, not the entire page, has at least one interactive child.
  if (out.variants.length < 2) {
    const candidates = document.querySelectorAll('section, article, .card, .demo, .example, .preview, div[data-component]');
    const taken = new Set();
    for (const el of candidates) {
      if (out.variants.length >= MAX_VARIANTS) break;
      const rect = el.getBoundingClientRect();
      if (rect.width < 200 || rect.width > 1300) continue;
      if (rect.height < 60 || rect.height > 800) continue;
      if (rect.bottom < 0 || rect.top > 5000) continue;
      // Must contain at least one interactive element to be a "UI piece"
      const interactives = el.querySelectorAll('button, a, input, select, [role="button"]');
      if (interactives.length < 1) continue;
      // De-duplicate near-identical blocks
      const sig = (el.tagName + ':' + Math.round(rect.width) + 'x' + Math.round(rect.height) +
                   ':' + (el.firstElementChild ? el.firstElementChild.tagName : ''));
      if (taken.has(sig)) continue;
      taken.add(sig);
      // outerHTML capped to keep LLM happy
      let html = el.outerHTML || '';
      if (html.length > 12000) html = html.slice(0, 12000);
      out.variants.push({
        mode: 'dom_capture',
        html: html,
        anchor_rect: { x: Math.round(rect.x), y: Math.round(rect.y + window.scrollY),
                       w: Math.round(rect.width), h: Math.round(rect.height) },
      });
    }
  }

  return out;
})()
"""


# ── LLM conversion (HTML → JSX + Arabic description in one call) ────────────

def _convert_system(locale: str = "ar") -> str:
    return load_prompt("skills/find_components", locale=locale)


async def _llm_convert(llm: Any, raw_html: str, query: str, source_host: str) -> dict[str, Any]:
    """One LLM call per variant. Returns a dict with name/jsx/description_ar/tags."""
    user = (
        f"USER WAS SEARCHING FOR: {query}\n"
        f"SOURCE SITE: {source_host}\n\n"
        f"RAW SNIPPET (HTML or JSX-ish):\n```\n{raw_html[:10000]}\n```"
    )
    try:
        data = await llm.chat_json(_convert_system(), user)
        if not isinstance(data, dict):
            raise ValueError("non-dict")
        return {
            "name": str(data.get("name") or "").strip() or "UnnamedComponent",
            "jsx": str(data.get("jsx") or "").strip(),
            "description_ar": str(data.get("description_ar") or "").strip(),
            "tags": [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()][:6],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning(f"LLM convert failed for {source_host}: {exc!s:.140}")
        return _fallback_jsx(raw_html, source_host)


def _fallback_jsx(raw_html: str, source_host: str) -> dict[str, Any]:
    """If the LLM call fails, produce a passable JSX wrapper by hand. Never
    leave a variant without a usable Component.jsx — the viewer needs one."""
    cleaned = raw_html
    cleaned = re.sub(r"\sclass=", " className=", cleaned)
    cleaned = re.sub(r"\sfor=", " htmlFor=", cleaned)
    # self-close void tags (best-effort)
    for tag in ("img", "input", "br", "hr", "meta", "link"):
        cleaned = re.sub(rf"<{tag}([^>]*?)>", rf"<{tag}\1 />", cleaned, flags=re.IGNORECASE)
    name = f"Component_{re.sub(r'[^a-zA-Z0-9]', '', source_host)[:24] or 'Snippet'}"
    jsx = f"export default function {name}() {{\n  return (\n    <>\n{cleaned}\n    </>\n  );\n}}\n"
    return {
        "name": name,
        "jsx": jsx,
        "description_ar": "مكوّن مُستخرَج تلقائيًا — لم يتوفر تحويل ذكي؛ المراجعة اليدوية مستحسنة.",
        "tags": ["fallback"],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(q: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_؀-ۿ]+", "_", q).strip("_")
    return (s or "components")[:64]


def _safe_filename(s: str) -> str:
    """Safe filesystem path segment, ASCII only — viewers expect this."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_") or "x"


def _host_of(u: str) -> str:
    try:
        return (urlparse(u).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


# ── Public API ───────────────────────────────────────────────────────────────

async def find_components(
    query: str,
    *,
    max_pages: int = 5,
    max_variants_per_page: int = 3,
    headless: bool = True,
) -> ComponentSearchResult:
    """Discover → visit → extract code → convert to JSX → write gallery.

    `max_pages` caps the search visit queue; `max_variants_per_page` caps
    how many separate components we pull off a single visited page.
    """
    slug = _slugify(query)
    ts = int(time.time())
    out_dir = settings.output_path / "components" / f"{slug}_{ts}"
    components_root = out_dir / "components"
    components_root.mkdir(parents=True, exist_ok=True)

    llm = get_provider(settings)
    search_agent = SearchAgent(llm)

    expanded = _query_expansion(query)
    research = await search_agent.research(goal=expanded[0], max_queries=max(3, len(expanded)),
                                           max_candidates=max_pages)
    candidates: list[RankedCandidate] = (research.visit_queue or research.candidates[:max_pages])[:max_pages]

    variants: list[ComponentVariant] = []
    counter = 0

    session = BrowserSession(headless=headless)
    await session.start()
    try:
        for cand in candidates:
            try:
                await session.goto(cand.url)
                await asyncio.sleep(1.5)
                # Take a full-page screenshot as a fallback preview
                full_shot_bytes = await session.screenshot()
                # Extract candidate snippets via JS
                raw = await session.eval_js(_EXTRACT_JS) or {}
                page_title = str(raw.get("page_title") or cand.title or "").strip()
                page_variants = (raw.get("variants") or [])[:max_variants_per_page]
            except Exception as exc:  # noqa: BLE001
                log.warning(f"visit {cand.url} failed: {exc!s:.140}")
                continue

            if not page_variants:
                log.info(f"  • no extractable variants on {cand.host}")
                continue

            for vi, v in enumerate(page_variants):
                counter += 1
                converted = await _llm_convert(llm, str(v.get("html") or ""), query, cand.host)
                comp_name = _safe_filename(converted["name"])
                variant_id = f"{counter:02d}_{comp_name}_{_safe_filename(cand.host)[:24]}"
                vdir = components_root / variant_id
                vdir.mkdir(parents=True, exist_ok=True)

                # Save the JSX, the raw source, and the Arabic readme.
                (vdir / "Component.jsx").write_text(converted["jsx"], encoding="utf-8")
                (vdir / "source.html").write_text(str(v.get("html") or ""), encoding="utf-8")
                readme = (
                    f"# {converted['name']}\n\n"
                    f"**المصدر:** <{cand.url}>\n\n"
                    f"**الموقع:** {cand.host}\n\n"
                    f"**الوسوم:** {', '.join(converted['tags']) or '—'}\n\n"
                    f"## الوصف\n\n{converted['description_ar']}\n"
                )
                (vdir / "README.md").write_text(readme, encoding="utf-8")

                # Cropped preview — best-effort. Falls back to the full
                # screenshot we already took.
                preview_path = vdir / "preview.png"
                try:
                    rect = v.get("anchor_rect") or {}
                    page = session.page
                    if page is not None and rect.get("w") and rect.get("h"):
                        await page.screenshot(
                            path=str(preview_path),
                            clip={
                                "x": max(0, float(rect["x"])),
                                "y": max(0, float(rect["y"])),
                                "width": min(1400.0, float(rect["w"])),
                                "height": min(1400.0, float(rect["h"])),
                            },
                            full_page=True,
                        )
                except Exception:
                    pass
                if not preview_path.exists():
                    preview_path.write_bytes(full_shot_bytes)

                variants.append(ComponentVariant(
                    variant_id=variant_id,
                    source_url=cand.url,
                    source_host=cand.host,
                    source_title=page_title,
                    name=converted["name"],
                    extraction_mode=str(v.get("mode") or "unknown"),
                    raw_html=str(v.get("html") or ""),
                    jsx_code=converted["jsx"],
                    description_ar=converted["description_ar"],
                    tags=converted["tags"],
                    preview=f"components/{variant_id}/preview.png",
                    component_file=f"components/{variant_id}/Component.jsx",
                    readme_file=f"components/{variant_id}/README.md",
                    source_file=f"components/{variant_id}/source.html",
                ))
                log.info(f"  ✔ variant {variant_id} ({converted['name']}, mode={v.get('mode')})")
    finally:
        await session.stop()
        try:
            await llm.close()
        except Exception:
            pass

    # ── Render the viewer + Arabic Markdown report ───────────────────
    viewer_html_str = render_viewer(query=query, variants=variants)
    (out_dir / "viewer.html").write_text(viewer_html_str, encoding="utf-8")

    report_md = _arabic_md(query, variants)
    (out_dir / "report.ar.md").write_text(report_md, encoding="utf-8")

    meta = {
        "query": query,
        "expanded_queries": expanded,
        "n_variants": len(variants),
        "created_at": ts,
        "variants": [v.to_dict() for v in variants],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"📚 {len(variants)} component variant(s) written → {out_dir}")

    return ComponentSearchResult(
        query=query,
        out_dir=str(out_dir),
        viewer_html=str(out_dir / "viewer.html"),
        report_md=str(out_dir / "report.ar.md"),
        variants=variants,
    )


def _arabic_md(query: str, variants: list[ComponentVariant]) -> str:
    """Companion Markdown index — quick scan, links to JSX files."""
    lines = [
        '<div dir="rtl" lang="ar">',
        "",
        f"# 🎨 مكوّنات للاستعلام: {query}",
        "",
        f"عدد الإصدارات المُستخرَجة: **{len(variants)}**",
        "",
        "افتح `viewer.html` لاستعراض المكوّنات بشكل تفاعلي مع كود ملوّن.",
        "",
    ]
    if not variants:
        lines.append("_(لم يتم استخراج أي مكوّن. جرّب استعلامًا أكثر تحديدًا.)_")
        lines.append("</div>")
        return "\n".join(lines)

    # Group by source host
    by_host: dict[str, list[ComponentVariant]] = {}
    for v in variants:
        by_host.setdefault(v.source_host or "?", []).append(v)

    for host, items in by_host.items():
        lines.append(f"## 📁 {host}")
        lines.append("")
        for v in items:
            tags = ", ".join(f"`{t}`" for t in v.tags) or "—"
            lines.append(f"### {v.name}")
            lines.append("")
            lines.append(f"- **المصدر:** <{v.source_url}>")
            lines.append(f"- **الوسوم:** {tags}")
            lines.append(f"- **الملف:** `{v.component_file}`")
            lines.append("")
            lines.append(f"> {v.description_ar}")
            lines.append("")
    lines.append("</div>")
    return "\n".join(lines)
