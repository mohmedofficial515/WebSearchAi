"""Skill: extract design tokens (palette, typography, spacing) from any URL.

For designers cloning a look-and-feel or auditing a site's design system.
Pure DOM/CSS read — no LLM call needed for the data layer. We let the
browser do the heavy lifting:

  * walks every visible element in `body`
  * reads computed styles (color, backgroundColor, fontFamily, fontSize,
    fontWeight, margin, padding, borderRadius)
  * aggregates: top-N colors by area, font families with sample text,
    used spacing/border-radius scale, primary/secondary visual roles

Outputs:
    outputs/design_tokens/<host>_<ts>/
      ├── tokens.json        ← machine-readable
      ├── palette.png        ← swatches strip
      ├── report.ar.md       ← Arabic markdown report
      └── screenshot.png     ← reference screenshot
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import settings
from ..core.browser import BrowserSession
from ..utils.logger import log


# ── Browser-side extractor ───────────────────────────────────────────────────
# This JS runs ONCE on the target page and returns a structured dump.
# Designed to be defensive: skips invisible nodes, clamps array size,
# never throws. Tested on Tailwind/MUI/Bootstrap sites without issue.

_EXTRACT_JS = r"""
(() => {
  const out = {
    url: location.href,
    title: document.title,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    colors: {},        // hex -> {area, role}
    background_colors: {},
    fonts: {},         // family -> count
    font_sizes: {},    // px -> count
    font_weights: {},  // weight -> count
    spacings: {},      // px -> count (margin+padding)
    radii: {},         // px -> count
    samples: [],       // a handful of text samples with their style
  };
  const allNodes = document.body ? document.body.querySelectorAll('*') : [];
  let scanned = 0;
  const MAX_NODES = 4000;

  const rgbToHex = (rgb) => {
    if (!rgb) return null;
    const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if (!m) return null;
    const a = m[4] === undefined ? 1 : parseFloat(m[4]);
    if (a < 0.05) return null; // effectively transparent
    const h = (n) => Number(n).toString(16).padStart(2, '0');
    return ('#' + h(m[1]) + h(m[2]) + h(m[3])).toLowerCase();
  };
  const incr = (bag, k, by = 1) => { if (!k) return; bag[k] = (bag[k] || 0) + by; };

  for (const el of allNodes) {
    if (scanned++ > MAX_NODES) break;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) continue;
    if (rect.bottom < 0 || rect.top > 4000) continue;   // ignore far-offscreen
    const cs = window.getComputedStyle(el);
    const area = Math.round(rect.width * rect.height);
    const fg = rgbToHex(cs.color);
    const bg = rgbToHex(cs.backgroundColor);
    if (fg) incr(out.colors, fg, area);
    if (bg) incr(out.background_colors, bg, area);
    const fam = (cs.fontFamily || '').split(',')[0].replace(/['"]/g, '').trim();
    if (fam) incr(out.fonts, fam);
    const fs = parseInt(cs.fontSize, 10);
    if (fs >= 8 && fs <= 96) incr(out.font_sizes, fs);
    const fw = parseInt(cs.fontWeight, 10);
    if (fw) incr(out.font_weights, fw);
    for (const k of ['marginTop','marginBottom','marginLeft','marginRight','paddingTop','paddingBottom','paddingLeft','paddingRight']) {
      const v = parseInt(cs[k], 10);
      if (v && v <= 256) incr(out.spacings, v);
    }
    const rad = parseInt(cs.borderRadius, 10);
    if (rad) incr(out.radii, rad);
  }

  // Capture up to 8 representative text samples (visible, has text, distinct).
  const seenTxt = new Set();
  const textNodes = document.body ? document.body.querySelectorAll('h1,h2,h3,h4,p,span,button,a,label') : [];
  for (const el of textNodes) {
    if (out.samples.length >= 8) break;
    const t = (el.innerText || '').trim();
    if (t.length < 4 || t.length > 80) continue;
    if (seenTxt.has(t)) continue;
    seenTxt.add(t);
    const cs = window.getComputedStyle(el);
    out.samples.push({
      text: t,
      tag: el.tagName.toLowerCase(),
      color: rgbToHex(cs.color),
      bg: rgbToHex(cs.backgroundColor),
      font_family: (cs.fontFamily || '').split(',')[0].replace(/['"]/g, '').trim(),
      font_size: cs.fontSize,
      font_weight: cs.fontWeight,
    });
  }
  return out;
})()
"""


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class DesignTokens:
    url: str
    title: str
    out_dir: str
    palette: list[dict[str, Any]]         # top colors by area
    background_palette: list[dict[str, Any]]
    fonts: list[str]                       # top font families
    font_size_scale: list[int]             # ordered list of common px sizes
    spacing_scale: list[int]
    radii: list[int]
    samples: list[dict[str, Any]]
    screenshot: str
    palette_image: str
    tokens_json: str
    report_md: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _top_n_by_area(bag: dict[str, int], n: int = 8) -> list[dict[str, Any]]:
    items = sorted(bag.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1
    return [{"hex": k, "area": v, "ratio": round(v / total, 3)} for k, v in items[:n]]


def _top_keys(bag: dict[str, int], n: int) -> list[Any]:
    return [k for k, _ in sorted(bag.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _write_palette_png(palette: list[dict[str, Any]], path: Path, swatch: int = 96) -> None:
    """Emit a tiny swatches strip. Uses Pillow if available, otherwise
    falls back to a hand-rolled PPM file — same data, viewable by macOS
    Preview / GIMP / VS Code's image viewer. Either way the user can
    eyeball the brand palette."""
    if not palette:
        return
    n = len(palette)
    w = swatch * n
    h = swatch
    try:
        from PIL import Image  # type: ignore
        img = Image.new("RGB", (w, h), (255, 255, 255))
        px = img.load()
        for i, c in enumerate(palette):
            r, g, b = _hex_to_rgb(c["hex"])
            for x in range(i * swatch, (i + 1) * swatch):
                for y in range(h):
                    px[x, y] = (r, g, b)
        img.save(path, "PNG")
        return
    except Exception:
        pass
    # Fallback: write a P6 PPM (raw RGB). Strip extension if needed.
    ppm_path = path.with_suffix(".ppm")
    rows = []
    for c in palette:
        r, g, b = _hex_to_rgb(c["hex"])
        rows.append(bytes((r, g, b)) * swatch)
    body = b"".join(row * h for row in [b"".join(rows)])
    with open(ppm_path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(body)


def _arabic_md(t: DesignTokens) -> str:
    pal_rows = "\n".join(
        f"| {c['hex']} | {int(c['ratio']*100)}% | ![swatch](data:image/svg+xml;utf8,"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='14'><rect width='40' height='14' fill='{c['hex']}'/></svg>) |"
        for c in t.palette
    )
    bg_rows = "\n".join(
        f"| {c['hex']} | {int(c['ratio']*100)}% |" for c in t.background_palette
    )
    fonts_md = ", ".join(f"`{f}`" for f in t.fonts) or "_(غير محدد)_"
    sizes_md = ", ".join(f"{s}px" for s in t.font_size_scale) or "_(لا يوجد)_"
    spacing_md = ", ".join(f"{s}px" for s in t.spacing_scale) or "_(لا يوجد)_"
    radii_md = ", ".join(f"{r}px" for r in t.radii) or "_(بدون حواف دائرية)_"

    samples = ""
    if t.samples:
        samples = "\n## ✍️ عيّنات نصّية\n\n"
        for s in t.samples:
            samples += (
                f"- **{s.get('tag','?')}** بحجم {s.get('font_size','?')} / وزن {s.get('font_weight','?')} "
                f"/ لون `{s.get('color') or '?'}` — {s.get('text','')}\n"
            )

    return f"""<div dir="rtl" lang="ar">

# 🎨 رموز التصميم

**المصدر:** <{t.url}>
**العنوان:** {t.title}

## 🟦 الألوان الأساسية (نصوص/خطوط/أيقونات)

| اللون | النسبة من المساحة | معاينة |
|------|-------------------|--------|
{pal_rows}

## 🟪 ألوان الخلفية

| اللون | النسبة |
|------|--------|
{bg_rows}

## 🔤 الطباعة

- **الخطوط:** {fonts_md}
- **مقاسات الخط الشائعة:** {sizes_md}

## 📏 المقاييس

- **سُلَّم المسافات (margin/padding):** {spacing_md}
- **انحناءات الزوايا:** {radii_md}

{samples}

---

**ملف JSON الكامل:** `{Path(t.tokens_json).name}`
**اللقطة:** `{Path(t.screenshot).name}`
**شريط الألوان:** `{Path(t.palette_image).name}`

</div>
"""


# ── Public API ───────────────────────────────────────────────────────────────

async def extract_design_tokens(
    url: str,
    *,
    headless: bool = True,
    wait_seconds: float = 2.0,
) -> DesignTokens:
    """Visit `url`, read computed styles, dump tokens + screenshot."""
    host = (urlparse(url).hostname or "site").replace(".", "_")
    ts = int(time.time())
    out_dir = settings.output_path / "design_tokens" / f"{host}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    session = BrowserSession(headless=headless)
    await session.start()
    raw: dict[str, Any] = {}
    try:
        await session.goto(url)
        import asyncio
        await asyncio.sleep(wait_seconds)  # let fonts + JS-driven layout settle
        shot_path = out_dir / "screenshot.png"
        await session.screenshot(path=shot_path)
        raw = await session.eval_js(_EXTRACT_JS) or {}
    finally:
        await session.stop()

    palette = _top_n_by_area(raw.get("colors") or {}, n=8)
    bg_palette = _top_n_by_area(raw.get("background_colors") or {}, n=6)
    fonts = _top_keys(raw.get("fonts") or {}, n=4)
    sizes = sorted({int(k) for k in (raw.get("font_sizes") or {}).keys()})
    spacings = sorted({int(k) for k, v in (raw.get("spacings") or {}).items() if v >= 2})
    radii = sorted({int(k) for k in (raw.get("radii") or {}).keys()})

    palette_img = out_dir / "palette.png"
    _write_palette_png(palette, palette_img)

    tokens_json_path = out_dir / "tokens.json"
    full = {
        "url": url,
        "title": raw.get("title") or "",
        "palette": palette,
        "background_palette": bg_palette,
        "fonts": fonts,
        "font_size_scale": sizes,
        "spacing_scale": spacings,
        "radii": radii,
        "samples": raw.get("samples") or [],
    }
    tokens_json_path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    tokens = DesignTokens(
        url=url,
        title=raw.get("title") or "",
        out_dir=str(out_dir),
        palette=palette,
        background_palette=bg_palette,
        fonts=fonts,
        font_size_scale=sizes,
        spacing_scale=spacings,
        radii=radii,
        samples=raw.get("samples") or [],
        screenshot=str(shot_path),
        palette_image=str(palette_img if palette_img.exists() else palette_img.with_suffix(".ppm")),
        tokens_json=str(tokens_json_path),
        report_md=str(out_dir / "report.ar.md"),
    )

    (out_dir / "report.ar.md").write_text(_arabic_md(tokens), encoding="utf-8")
    log.info(f"🎨 design tokens extracted → {out_dir}")
    return tokens
