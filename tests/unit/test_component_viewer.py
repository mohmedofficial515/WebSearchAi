"""Tests for the upgraded find_components skill + viewer.html renderer.

These tests cover the pure helpers (no browser, no LLM, no network):
  * the LLM-free `_fallback_jsx` builder must always produce a usable
    component when the LLM call would have failed;
  * the viewer template embeds variant data correctly, preserves Arabic,
    and exposes a `language-javascript` / `language-xml` highlight hook;
  * the companion Markdown report groups variants by host and links the
    saved `.jsx` files.
"""
from __future__ import annotations

import json

import pytest


# ── _fallback_jsx (LLM-free conversion) ─────────────────────────────────────

@pytest.mark.unit
def test_fallback_jsx_self_closes_void_tags_and_renames_class():
    from src.skills.find_components import _fallback_jsx
    raw = '<div class="card"><img src="a.png"><input type="text"></div>'
    out = _fallback_jsx(raw, "flowbite.com")
    jsx = out["jsx"]
    assert "className=" in jsx
    assert "class=" not in jsx.replace("className=", "")  # no bare class=
    # void-element self-closing — be defensive about whitespace placement
    assert "<img" in jsx and "/>" in jsx
    assert "<input" in jsx and "/>" in jsx
    assert "export default function" in jsx
    assert out["tags"] == ["fallback"]


@pytest.mark.unit
def test_fallback_jsx_component_name_is_valid_identifier():
    from src.skills.find_components import _fallback_jsx
    out = _fallback_jsx("<div/>", "ui.shadcn.com")
    # Must be a valid JS identifier (no dots, hyphens, etc.)
    import re
    assert re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", out["name"]), out["name"]


@pytest.mark.unit
def test_fallback_jsx_arabic_description_present():
    from src.skills.find_components import _fallback_jsx
    out = _fallback_jsx("<button>OK</button>", "x.com")
    # Some Arabic content present (any RTL letter is enough).
    assert any("؀" <= ch <= "ۿ" for ch in out["description_ar"])


# ── Query expansion ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_query_expansion_named_library_skips_competitors():
    from src.skills.find_components import _query_expansion
    qs = _query_expansion("shadcn dashboard")
    joined = " ".join(qs).lower()
    # tailwind / bootstrap variants should not be added when shadcn is named.
    assert "tailwind " not in joined
    assert "bootstrap " not in joined


# ── component_viewer.render_viewer ──────────────────────────────────────────

def _make_variant(**overrides):
    """Build a ComponentVariant with sensible defaults for testing."""
    from src.skills.find_components import ComponentVariant
    base = dict(
        variant_id="01_PrimaryNavbar_flowbite_com",
        source_url="https://flowbite.com/blocks/marketing/navbars/",
        source_host="flowbite.com",
        source_title="Flowbite Navbars",
        name="PrimaryNavbar",
        extraction_mode="code_block",
        raw_html='<nav class="px-4 py-2"><span>Brand</span></nav>',
        jsx_code=(
            'export default function PrimaryNavbar() {\n'
            '  return (\n'
            '    <nav className="px-4 py-2"><span>Brand</span></nav>\n'
            '  );\n'
            '}\n'
        ),
        description_ar="شريط تنقّل بسيط بخلفية فاتحة لصفحات الهبوط.",
        tags=["navbar", "tailwind", "responsive"],
        preview="components/01_PrimaryNavbar_flowbite_com/preview.png",
        component_file="components/01_PrimaryNavbar_flowbite_com/Component.jsx",
        readme_file="components/01_PrimaryNavbar_flowbite_com/README.md",
        source_file="components/01_PrimaryNavbar_flowbite_com/source.html",
    )
    base.update(overrides)
    return ComponentVariant(**base)


@pytest.mark.unit
def test_viewer_embeds_variant_data_and_highlight_languages():
    from src.reports.component_viewer import render_viewer
    html = render_viewer("tailwind navbar", [_make_variant()])
    # Variant data is embedded as JSON
    assert "PrimaryNavbar" in html
    assert "شريط تنقّل" in html
    # highlight.js hooks are present for both code panels
    assert "language-javascript" in html
    assert "language-xml" in html
    # Sidebar grouping uses the host name
    assert "flowbite.com" in html
    # RTL root + Tajawal font
    assert 'dir="rtl"' in html
    assert "Tajawal" in html


@pytest.mark.unit
def test_viewer_handles_empty_variants_without_crashing():
    from src.reports.component_viewer import render_viewer
    html = render_viewer("nothing here", [])
    # Renders the shell even with zero variants; nothing should explode.
    assert "معرض المكوّنات" in html
    # Embedded variants list is an empty array
    assert "VARIANTS = []" in html


@pytest.mark.unit
def test_viewer_accepts_dicts_not_just_dataclasses():
    """render_viewer must accept either ComponentVariant or plain dicts."""
    from src.reports.component_viewer import render_viewer
    raw = {
        "variant_id": "x", "source_url": "https://a.io",
        "source_host": "a.io", "source_title": "A",
        "name": "X", "extraction_mode": "code_block",
        "raw_html": "<div/>", "jsx_code": "export default function X(){return <div/>}",
        "description_ar": "وصف عربي.", "tags": [],
        "preview": "p.png", "component_file": "X.jsx",
        "readme_file": "README.md", "source_file": "source.html",
    }
    html = render_viewer("q", [raw])
    assert '"variant_id": "x"' in html or '"variant_id":"x"' in html


@pytest.mark.unit
def test_viewer_escapes_html_in_query_but_keeps_json_literal_safe():
    from src.reports.component_viewer import render_viewer
    html = render_viewer("<script>alert(1)</script>", [])
    # The displayed-as-text version must be escaped.
    assert "&lt;script&gt;" in html
    # The JSON-literal copy (consumed by JS, not rendered) is allowed
    # to be the JSON-escaped form — what matters is that no literal
    # <script>alert(1)</script> survives as actual HTML.
    # Count occurrences of the bare unescaped tag — must be 0.
    assert "<script>alert(1)</script>" not in html


# ── _arabic_md companion report ─────────────────────────────────────────────

@pytest.mark.unit
def test_arabic_md_groups_variants_by_host():
    from src.skills.find_components import _arabic_md
    v1 = _make_variant(source_host="flowbite.com", name="NavA",
                       variant_id="01_NavA", component_file="components/01_NavA/Component.jsx")
    v2 = _make_variant(source_host="tailwindui.com", name="NavB",
                       variant_id="02_NavB", component_file="components/02_NavB/Component.jsx")
    md = _arabic_md("navbar", [v1, v2])
    assert "📁 flowbite.com" in md
    assert "📁 tailwindui.com" in md
    assert "NavA" in md and "NavB" in md
    # Each variant links its .jsx file
    assert "01_NavA/Component.jsx" in md
    assert "02_NavB/Component.jsx" in md


@pytest.mark.unit
def test_arabic_md_handles_zero_variants():
    from src.skills.find_components import _arabic_md
    md = _arabic_md("nothing", [])
    assert "لم يتم استخراج" in md
