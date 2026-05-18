"""Self-contained component viewer HTML.

Renders a single-file SPA the operator can open straight off the disk
(no build step, no local server needed). All variant data is embedded
as a JSON blob inside a `<script>` tag; the UI uses vanilla JS for
interaction plus highlight.js from a CDN for syntax coloring.

UX:
  ┌──────────────────────────────────────────────────────────────────┐
  │ 🎨  navbar tailwind                       12 إصدار  ·  3 مواقع   │
  ├─────────────┬────────────────────────────────────────────────────┤
  │ 📁 tailwind │  PrimaryNavbar                                     │
  │ • Navbar 1  │  ────────────────────────────────────────────      │
  │ • Navbar 2  │  [🖼 Preview] [⚛ JSX] [⬚ HTML] [📝 وصف]            │
  │             │                                                    │
  │ 📁 flowbite │   ┌────────────────────────────┐                   │
  │ • Brand H   │   │  <component preview here>   │                   │
  │             │   └────────────────────────────┘                   │
  │             │                                                    │
  │             │   description in Arabic                            │
  └─────────────┴────────────────────────────────────────────────────┘

The page is RTL-aware (Arabic descriptions) but the code panels stay
LTR so syntax highlighting reads correctly.
"""
from __future__ import annotations

import html
import json
from typing import Any


_HTML_TEMPLATE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8" />
<title>🎨 معرض المكوّنات — {query_safe}</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/styles/atom-one-dark.min.css" />
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/lib/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/languages/javascript.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.10.0/languages/xml.min.js"></script>
<style>
  :root {{
    --bg: #0b0d12;
    --panel: #11141b;
    --panel-2: #161a23;
    --border: #232838;
    --text: #e7e9ee;
    --muted: #98a0b3;
    --accent: #6c8cff;
    --accent-2: #4ee0c2;
    --ok: #4ad991;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; height: 100%;
    background: var(--bg); color: var(--text);
    font-family: 'Tajawal', 'Inter', system-ui, sans-serif;
  }}
  .layout {{ display: grid; grid-template-columns: 280px 1fr; height: 100vh; }}

  /* ─── Top bar (spans both columns) ─── */
  .topbar {{
    grid-column: 1 / -1;
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 22px;
    border-bottom: 1px solid var(--border);
    background: rgba(10,12,18,0.85); backdrop-filter: blur(8px);
  }}
  .topbar h1 {{ font-size: 18px; margin: 0; font-weight: 700; }}
  .topbar .meta {{ color: var(--muted); font-size: 13px; }}

  .layout {{ grid-template-rows: auto 1fr; }}

  /* ─── Sidebar ─── */
  .side {{
    border-left: 1px solid var(--border);
    background: var(--panel);
    overflow-y: auto;
    padding: 12px 8px;
  }}
  .side input {{
    width: 100%;
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 10px; border-radius: 8px;
    font-family: inherit; font-size: 13px;
    margin-bottom: 12px;
    direction: rtl; text-align: right;
  }}
  .side .group {{ margin-bottom: 14px; }}
  .side .group-head {{
    color: var(--muted); font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
    padding: 4px 8px; direction: ltr; text-align: right;
  }}
  .side .item {{
    display: flex; flex-direction: column; gap: 2px;
    padding: 8px 10px; border-radius: 8px;
    cursor: pointer;
    border: 1px solid transparent;
  }}
  .side .item:hover {{ background: var(--panel-2); }}
  .side .item.active {{
    background: rgba(108,140,255,0.12);
    border-color: rgba(108,140,255,0.3);
  }}
  .side .item .name {{ font-weight: 600; font-size: 14px; }}
  .side .item .sub  {{ color: var(--muted); font-size: 11px; direction: ltr; text-align: right; }}

  /* ─── Main panel ─── */
  .main {{ overflow-y: auto; padding: 22px 26px; }}
  .empty {{
    color: var(--muted); padding: 60px 20px;
    text-align: center; font-size: 14px;
  }}
  .head {{
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 14px; margin-bottom: 16px;
  }}
  .head h2 {{ font-size: 22px; margin: 0; }}
  .head .source {{
    color: var(--accent); font-size: 13px;
    direction: ltr; text-decoration: none;
  }}
  .head .pill {{
    font-size: 11px; padding: 3px 8px;
    background: var(--panel-2); border: 1px solid var(--border);
    border-radius: 999px; color: var(--muted);
  }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }}
  .tags .tag {{
    font-size: 11px; padding: 2px 8px;
    background: rgba(78,224,194,0.08);
    border: 1px solid rgba(78,224,194,0.25);
    color: var(--accent-2);
    border-radius: 999px;
  }}

  .description {{
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-right: 3px solid var(--accent);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 14px 0;
    line-height: 1.85;
    font-size: 15px;
  }}

  .tabs {{
    display: flex; gap: 4px;
    border-bottom: 1px solid var(--border);
    margin: 18px 0 0;
  }}
  .tabs button {{
    background: transparent; color: var(--muted);
    border: none; border-bottom: 2px solid transparent;
    padding: 8px 14px; cursor: pointer;
    font-family: inherit; font-size: 13px; font-weight: 500;
  }}
  .tabs button.active {{
    color: var(--text);
    border-bottom-color: var(--accent);
  }}
  .pane {{ display: none; padding: 18px 0; }}
  .pane.active {{ display: block; }}

  .preview {{
    background: #000;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0; overflow: hidden;
    max-height: 720px; display: flex; align-items: center; justify-content: center;
  }}
  .preview img {{ max-width: 100%; max-height: 720px; display: block; }}

  /* ─── Code panel ─── */
  .code-wrap {{
    background: #0b0d12;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    position: relative;
    direction: ltr;
  }}
  .code-toolbar {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel-2);
    direction: ltr;
  }}
  .code-toolbar .lang {{ color: var(--muted); font-size: 11px; font-family: 'JetBrains Mono', monospace; }}
  .code-toolbar button {{
    background: var(--panel); color: var(--text);
    border: 1px solid var(--border);
    padding: 4px 10px; border-radius: 6px;
    font-size: 12px; cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
  }}
  .code-toolbar button:hover {{ background: var(--bg); }}
  .code-wrap pre {{
    margin: 0;
    padding: 14px 18px;
    overflow-x: auto;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 13px;
    line-height: 1.6;
    direction: ltr; text-align: left;
    max-height: 60vh;
  }}
  .copy-feedback {{
    position: absolute; top: 8px; left: 8px;
    background: var(--ok); color: #000;
    padding: 4px 10px; border-radius: 6px; font-size: 11px;
    opacity: 0; transition: opacity .2s;
    direction: ltr;
  }}
  .copy-feedback.show {{ opacity: 1; }}
</style>
</head>
<body>

<div class="layout">

  <header class="topbar">
    <div>
      <h1>🎨 معرض المكوّنات</h1>
      <div class="meta">الاستعلام: <strong>{query_safe}</strong></div>
    </div>
    <div class="meta">
      <strong id="meta-count">0</strong> إصدار &nbsp;·&nbsp;
      <strong id="meta-hosts">0</strong> مصدر
    </div>
  </header>

  <aside class="side">
    <input type="search" id="filter" placeholder="🔎 ابحث داخل المعرض…" />
    <div id="groups"></div>
  </aside>

  <main class="main" id="main">
    <div class="empty">اختر مكوّنًا من القائمة الجانبية للبدء.</div>
  </main>

</div>

<script>
  // ─── Embedded data — produced server-side ───
  const VARIANTS = {variants_json};
  const QUERY = {query_json};

  // ─── Sidebar grouping by source host ───
  function escapeHtml(s) {{
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  }}

  const groupsEl = document.getElementById('groups');
  const metaCount = document.getElementById('meta-count');
  const metaHosts = document.getElementById('meta-hosts');

  function renderSidebar(filterText = '') {{
    const ft = filterText.trim().toLowerCase();
    const filtered = !ft ? VARIANTS : VARIANTS.filter(v =>
      (v.name + ' ' + v.source_host + ' ' + (v.tags||[]).join(' ') + ' ' + (v.description_ar||''))
        .toLowerCase().includes(ft));
    const byHost = {{}};
    filtered.forEach(v => {{
      const h = v.source_host || '—';
      (byHost[h] = byHost[h] || []).push(v);
    }});
    metaCount.textContent = filtered.length;
    metaHosts.textContent = Object.keys(byHost).length;

    groupsEl.innerHTML = Object.keys(byHost).map(host => `
      <div class="group">
        <div class="group-head">📁 ${{escapeHtml(host)}}</div>
        ${{byHost[host].map(v => `
          <div class="item" data-id="${{escapeHtml(v.variant_id)}}">
            <span class="name">${{escapeHtml(v.name)}}</span>
            <span class="sub">${{escapeHtml(v.extraction_mode)}} · ${{(v.tags||[]).slice(0,3).map(escapeHtml).join(' · ')}}</span>
          </div>
        `).join('')}}
      </div>
    `).join('') || '<div class="empty">لا نتائج مطابقة.</div>';

    groupsEl.querySelectorAll('.item').forEach(el =>
      el.addEventListener('click', () => selectVariant(el.dataset.id)));
  }}

  document.getElementById('filter').addEventListener('input', e => renderSidebar(e.target.value));

  // ─── Main panel rendering ───
  function selectVariant(variantId) {{
    document.querySelectorAll('.item').forEach(el =>
      el.classList.toggle('active', el.dataset.id === variantId));
    const v = VARIANTS.find(x => x.variant_id === variantId);
    if (!v) return;
    const tagsHtml = (v.tags || []).map(t => `<span class="tag">${{escapeHtml(t)}}</span>`).join('');
    document.getElementById('main').innerHTML = `
      <div class="head">
        <h2>${{escapeHtml(v.name)}}</h2>
        <a class="source" href="${{escapeHtml(v.source_url)}}" target="_blank" rel="noopener">${{escapeHtml(v.source_host)}} ↗</a>
        <span class="pill">${{escapeHtml(v.extraction_mode)}}</span>
      </div>
      <div class="tags">${{tagsHtml}}</div>

      <div class="description">${{escapeHtml(v.description_ar || '—')}}</div>

      <div class="tabs">
        <button class="active" data-pane="preview">🖼 معاينة</button>
        <button data-pane="jsx">⚛ JSX</button>
        <button data-pane="html">⬚ HTML أصلي</button>
      </div>

      <div class="pane active" id="pane-preview">
        <div class="preview"><img src="${{escapeHtml(v.preview)}}" alt="${{escapeHtml(v.name)}}" /></div>
      </div>

      <div class="pane" id="pane-jsx">
        <div class="code-wrap">
          <div class="code-toolbar">
            <span class="lang">JSX · ${{escapeHtml(v.component_file)}}</span>
            <button data-copy="jsx">📋 نسخ</button>
          </div>
          <pre><code class="language-javascript">${{escapeHtml(v.jsx_code)}}</code></pre>
          <div class="copy-feedback" id="fb-jsx">تم النسخ ✓</div>
        </div>
      </div>

      <div class="pane" id="pane-html">
        <div class="code-wrap">
          <div class="code-toolbar">
            <span class="lang">HTML · ${{escapeHtml(v.source_file)}}</span>
            <button data-copy="html">📋 نسخ</button>
          </div>
          <pre><code class="language-xml">${{escapeHtml(v.raw_html)}}</code></pre>
          <div class="copy-feedback" id="fb-html">تم النسخ ✓</div>
        </div>
      </div>
    `;

    // Wire tabs
    document.querySelectorAll('.tabs button').forEach(b =>
      b.addEventListener('click', () => {{
        document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.pane').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        document.getElementById('pane-' + b.dataset.pane).classList.add('active');
      }}));

    // Wire copy buttons
    document.querySelectorAll('[data-copy]').forEach(b =>
      b.addEventListener('click', () => {{
        const which = b.dataset.copy;
        const text = which === 'jsx' ? v.jsx_code : v.raw_html;
        navigator.clipboard.writeText(text).then(() => {{
          const fb = document.getElementById('fb-' + which);
          fb.classList.add('show');
          setTimeout(() => fb.classList.remove('show'), 1200);
        }});
      }}));

    // Syntax highlight
    if (window.hljs) document.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  }}

  // ─── Boot ───
  renderSidebar('');
  if (VARIANTS.length) selectVariant(VARIANTS[0].variant_id);
</script>

</body>
</html>"""


def _json_for_script(obj: Any) -> str:
    """JSON-encode `obj` for safe inlining inside an HTML `<script>` block.

    The closing tag `</script>` (or `</style>`) inside a JSON string breaks
    out of the surrounding tag — this is the canonical XSS sink for
    server-rendered JSON. Per the HTML spec, the JSON-safe way is to
    escape every `<` that precedes `/`, `!`, or `script`/`style` so the
    HTML parser never sees a closing tag, while the JSON parser still
    accepts the string (JSON allows `\\/` and `\\u003C`).
    """
    raw = json.dumps(obj, ensure_ascii=False)
    return (
        raw
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def render_viewer(query: str, variants: list[Any]) -> str:
    """Produce the self-contained `viewer.html` for a list of variants.

    `variants` is a list of `ComponentVariant` (we accept any object with
    `to_dict()`). Anything not serializable becomes a string.
    """
    serializable = []
    for v in variants:
        if hasattr(v, "to_dict"):
            serializable.append(v.to_dict())
        elif isinstance(v, dict):
            serializable.append(v)
        else:
            serializable.append({"variant_id": str(v), "name": str(v)})

    return _HTML_TEMPLATE.format(
        query_safe=html.escape(query or ""),
        query_json=_json_for_script(query or ""),
        variants_json=_json_for_script(serializable),
    )
