"""Extract a compact, LLM-friendly snapshot of the current page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .browser import BrowserSession

# Heavy JS that walks the DOM and emits a labeled list of interactive
# elements (links, buttons, inputs, selects, textareas, role=button).
# Each element gets a numeric index the LLM can reference: [12] click etc.
ELEMENT_INDEX_JS = r"""
(() => {
  const out = [];
  const tags = ['a','button','input','select','textarea','label'];

  const isVisible = el => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0
      && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };

  // Check if the element at the center point is actually THIS element (or a descendant).
  // This catches elements hidden behind overlays/modals/z-index layers.
  const isClickable = el => {
    const r = el.getBoundingClientRect();
    const cx = r.x + r.width / 2;
    const cy = r.y + r.height / 2;
    if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) return false;
    const top = document.elementFromPoint(cx, cy);
    return top === el || el.contains(top);
  };

  // Detect overlay/modal elements: fixed/absolute positioned, high z-index,
  // large area, and in front of other content.
  const detectOverlays = () => {
    const overlays = [];
    const vw = window.innerWidth, vh = window.innerHeight;
    const all = Array.from(document.querySelectorAll('*'));
    for (const el of all) {
      const s = window.getComputedStyle(el);
      const z = parseInt(s.zIndex) || 0;
      if (z < 10) continue;
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
      const r = el.getBoundingClientRect();
      if (r.width < 100 || r.height < 80) continue;
      const coverage = (r.width * r.height) / (vw * vh);
      if (coverage < 0.05) continue;
      const pos = s.position;
      if (pos !== 'fixed' && pos !== 'absolute' && pos !== 'sticky') continue;
      const text = (el.innerText || '').trim().slice(0, 100);
      overlays.push({
        tag: el.tagName.toLowerCase(), z, text,
        coverage: Math.round(coverage * 100),
        rect: { left: r.left, top: r.top, right: r.right, bottom: r.bottom }
      });
    }
    overlays.sort((a, b) => b.z - a.z);
    return overlays.slice(0, 5);
  };

  const overlays = detectOverlays();
  const hasOverlay = overlays.length > 0;

  const all = Array.from(document.querySelectorAll('*'));
  let idx = 0;
  for (const el of all) {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || '';
    const interactive = tags.includes(tag)
      || role === 'button' || role === 'link' || role === 'textbox'
      || el.hasAttribute('onclick') || el.getAttribute('tabindex') === '0';
    if (!interactive) continue;
    if (!isVisible(el)) continue;
    const clickable = isClickable(el);
    const text = (el.innerText || el.value || el.placeholder || '').trim().slice(0,120);
    const r = el.getBoundingClientRect();
    const attrs = {};
    for (const a of ['id','name','type','placeholder','aria-label','href','value','title']) {
      const v = el.getAttribute(a);
      if (v) attrs[a] = v.slice(0,120);
    }
    out.push({
      i: idx++,
      tag, role,
      text,
      attrs,
      clickable,
      box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
    });
    el.setAttribute('data-wsai-idx', String(idx-1));
  }

  // ── Close-button candidates ────────────────────────────────────────────
  // When an overlay is detected, rank already-indexed clickable elements by
  // how likely they are to be the "close" / "dismiss" / "no thanks" control.
  // The LLM gets these as ready-to-click [index]es so it doesn't have to
  // scan 80 elements looking for an × icon.
  const findCloseCandidates = (overlayRect) => {
    const signals = ['close','dismiss','×','✕','✖',
                     'إغلاق','اغلاق','رفض','لا شكرا','لا شكراً','لاحقا','لاحقاً',
                     'تخطي','إلغاء','الغاء','تجاهل',
                     'skip','no thanks','no, thanks','cancel','later','not now',
                     'maybe later','reject'];
    const cands = [];
    for (const e of out) {
      if (!e.clickable) continue;
      const hay = ((e.text || '') + ' ' +
                   (e.attrs['aria-label'] || '') + ' ' +
                   (e.attrs['title'] || '') + ' ' +
                   (e.attrs['id'] || '') + ' ' +
                   (e.attrs['name'] || '')).toLowerCase();
      let score = 0;
      let matched = '';
      for (const sig of signals) {
        if (hay.includes(sig)) { score += 5; matched = sig; break; }
      }
      if (overlayRect) {
        const cx = e.box.x + e.box.w / 2;
        const cy = e.box.y + e.box.h / 2;
        const inOverlay = (cx >= overlayRect.left && cx <= overlayRect.right &&
                          cy >= overlayRect.top && cy <= overlayRect.bottom);
        if (inOverlay) {
          score += 2;
          // Top-right corner of the overlay — classic close-button slot.
          const inTopRight = (e.box.x + e.box.w > overlayRect.right - 80) &&
                             (e.box.y < overlayRect.top + 80);
          if (inTopRight && e.box.w <= 80 && e.box.h <= 80) score += 3;
        }
      }
      // Tiny near-square icon-button: likely an × glyph.
      if (e.box.w > 0 && e.box.w <= 50 && e.box.h <= 50 &&
          Math.abs(e.box.w - e.box.h) <= 12) score += 1;
      if (score >= 5) {
        cands.push({ index: e.i, text: (e.text||'').slice(0,60), score, matched });
      }
    }
    return cands.sort((a, b) => b.score - a.score).slice(0, 5);
  };

  const closeCandidates = overlays.length > 0
    ? findCloseCandidates(overlays[0].rect)
    : [];

  return {
    elements: out, overlays, has_overlay: hasOverlay,
    close_candidates: closeCandidates,
  };
})();
"""


@dataclass
class Snapshot:
    url: str
    title: str
    elements: list[dict[str, Any]] = field(default_factory=list)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    has_overlay: bool = False
    close_candidates: list[dict[str, Any]] = field(default_factory=list)
    screenshot_b64: str | None = None
    screenshot_bytes: bytes | None = None

    def render_for_llm(self, max_elements: int = 80) -> str:
        lines = [f"URL: {self.url}", f"TITLE: {self.title}"]

        if self.has_overlay:
            lines.append("")
            lines.append("⚠️  OVERLAY/MODAL DETECTED — the entire page underneath is BLOCKED.")
            lines.append("   You MUST clear this overlay BEFORE any other action.")
            lines.append("   Overlay info:")
            for ov in self.overlays[:3]:
                lines.append(f"     - <{ov['tag']}> z={ov['z']} coverage={ov['coverage']}% text={ov['text']!r}")
            lines.append("")
            lines.append("   ▶ REQUIRED ACTION SEQUENCE (try in THIS order):")
            lines.append('     1. {"action":"dismiss_overlay"}   ← AUTO: tries 20+ close-button')
            lines.append("        selectors, cookie buttons, Escape. Handles ~95% of cases.")
            if self.close_candidates:
                lines.append("     2. If dismiss_overlay reports failure, click one of these")
                lines.append("        CLOSE-BUTTON CANDIDATES (ranked by likelihood):")
                for c in self.close_candidates[:5]:
                    txt = (c.get("text") or "").replace("\n", " ").strip()[:50]
                    matched = c.get("matched") or ""
                    lines.append(
                        f'        → {{"action":"click","index":{c["index"]}}}  '
                        f'(score={c["score"]}, matched={matched!r}, text={txt!r})'
                    )
            else:
                lines.append("     2. No close-button candidate detected in the DOM. If")
                lines.append("        dismiss_overlay also fails, reload the page:")
                lines.append('        {"action":"goto","url":"<current url>"} — some overlays')
                lines.append("        do not reappear after a fresh load.")
            lines.append("")
            lines.append("   ⛔ DO NOT press Escape repeatedly — once is enough, then switch.")
            lines.append("   ⛔ DO NOT click any element behind the overlay — each costs a 30s timeout.")

        lines.append("")
        lines.append("INTERACTIVE ELEMENTS (clickable=True means NOT blocked by overlay):")
        blocked_count = 0
        shown = 0
        for e in self.elements:
            clickable = e.get("clickable", True)
            if not clickable:
                blocked_count += 1
                continue
            if shown >= max_elements:
                break
            a = e["attrs"]
            label_bits: list[str] = []
            for key in ("placeholder", "aria-label", "name", "id", "type", "href", "title"):
                if a.get(key):
                    label_bits.append(f"{key}={a[key]!r}")
            label = " ".join(label_bits)
            txt = (e["text"] or "").replace("\n", " ")
            lines.append(f"[{e['i']}] <{e['tag']}> \"{txt}\" {label}".rstrip())
            shown += 1

        if blocked_count:
            lines.append(f"... ({blocked_count} elements hidden behind overlay — not shown)")
        elif len(self.elements) > max_elements:
            lines.append(f"... (+{len(self.elements) - max_elements} more elements)")
        return "\n".join(lines)


class Perception:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session

    async def snapshot(self, include_screenshot: bool = True) -> Snapshot:
        import asyncio, base64
        url = await self.session.url()
        try:
            title = await self.session.title()
        except Exception:
            await asyncio.sleep(0.5)
            try:
                title = await self.session.title()
            except Exception:
                title = ""
        elements: list[dict[str, Any]] = []
        overlays: list[dict[str, Any]] = []
        has_overlay = False
        close_candidates: list[dict[str, Any]] = []
        try:
            raw = await self.session.eval_js(ELEMENT_INDEX_JS)
            if isinstance(raw, dict):
                elements = raw.get("elements") or []
                overlays = raw.get("overlays") or []
                has_overlay = bool(raw.get("has_overlay"))
                close_candidates = raw.get("close_candidates") or []
            elif isinstance(raw, list):
                elements = raw
        except Exception:
            pass
        shot: bytes | None = None
        if include_screenshot:
            try:
                shot = await self.session.screenshot()
            except Exception:
                shot = None

        return Snapshot(
            url=url,
            title=title,
            elements=elements,
            overlays=overlays,
            has_overlay=has_overlay,
            close_candidates=close_candidates,
            screenshot_bytes=shot,
            screenshot_b64=base64.b64encode(shot).decode() if shot else None,
        )

    @staticmethod
    def selector_for_index(idx: int) -> str:
        return f"[data-wsai-idx='{idx}']"
