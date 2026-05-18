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
      box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
    });
    el.setAttribute('data-wsai-idx', String(idx-1));
  }
  return out;
})();
"""


@dataclass
class Snapshot:
    url: str
    title: str
    elements: list[dict[str, Any]] = field(default_factory=list)
    screenshot_b64: str | None = None
    screenshot_bytes: bytes | None = None

    def render_for_llm(self, max_elements: int = 80) -> str:
        lines = [f"URL: {self.url}", f"TITLE: {self.title}", "", "INTERACTIVE ELEMENTS:"]
        for e in self.elements[:max_elements]:
            a = e["attrs"]
            label_bits: list[str] = []
            for key in ("placeholder", "aria-label", "name", "id", "type", "href", "title"):
                if a.get(key):
                    label_bits.append(f"{key}={a[key]!r}")
            label = " ".join(label_bits)
            txt = (e["text"] or "").replace("\n", " ")
            lines.append(f"[{e['i']}] <{e['tag']}> \"{txt}\" {label}".rstrip())
        if len(self.elements) > max_elements:
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
        try:
            elements = await self.session.eval_js(ELEMENT_INDEX_JS) or []
        except Exception:
            elements = []
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
            screenshot_bytes=shot,
            screenshot_b64=base64.b64encode(shot).decode() if shot else None,
        )

    @staticmethod
    def selector_for_index(idx: int) -> str:
        return f"[data-wsai-idx='{idx}']"
