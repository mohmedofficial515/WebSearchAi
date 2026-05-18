"""Unit tests for the Arabic Markdown report renderer.

Tests are pure-string assertions — no LLM, no network. The renderer
takes a `TaskResult.to_dict()` and must:
  * never crash on partial/missing fields
  * preserve Arabic content verbatim
  * include every section when data is present
  * skip empty sections
  * emit RTL-friendly markup
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _minimal_result() -> dict:
    return {
        "task_id": "abc123",
        "goal": "تطبيق ديل للعقارات السعودية",
        "success": True,
        "confidence": 0.85,
        "reason": "تم العثور على المعلومة",
        "summary": "تطبيق ديل هو منصة سعودية للعقارات. dealapp.sa",
        "artifacts_dir": "outputs/sessions/abc123",
        "extractions": [],
        "steps": [],
        "plan": {
            "goal": "g", "success_criteria": [], "subtasks": [],
            "research": {
                "queries": ["تطبيق ديل للعقارات السعودية", "ديل عقارات السعودية"],
                "candidates_seen": [
                    {"url": "https://dealapp.sa/", "host": "dealapp.sa",
                     "heuristic_score": 0.8, "llm_score": 0.95, "final_score": 0.89,
                     "llm_reason": "الموقع الرسمي للتطبيق"},
                    {"url": "https://dell.com/", "host": "dell.com",
                     "heuristic_score": 0.1, "llm_score": 0.05, "final_score": 0.07,
                     "llm_reason": "علامة تجارية مختلفة"},
                ],
                "useful_sources": [
                    {"url": "https://dealapp.sa/", "title": "Deal App",
                     "verdict": "يحتوي على وصف كامل للتطبيق",
                     "useful_facts": ["متاح على iOS و Android", "يغطي السعودية"],
                     "score": 0.9}
                ],
                "synthesis": {
                    "answer": "تطبيق ديل هو منصة عقارية سعودية",
                    "citations": [{"url": "https://dealapp.sa/", "quote": "متخصص في عقارات السعودية"}],
                    "confidence": 0.88, "caveats": "",
                    "feedback": "الإجابة مدعومة بمصدر رسمي",
                    "addresses_goal": True, "well_cited": True,
                },
            },
        },
    }


# ── Core rendering ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_report_preserves_arabic_content():
    from src.reports import render_arabic_report
    md = render_arabic_report(_minimal_result())
    assert "تطبيق ديل للعقارات السعودية" in md
    assert "dealapp.sa" in md
    assert "متاح على iOS و Android" in md


@pytest.mark.unit
def test_report_emits_rtl_markers():
    from src.reports import render_arabic_report
    md = render_arabic_report(_minimal_result())
    assert 'dir="rtl"' in md
    assert 'lang="ar"' in md


@pytest.mark.unit
def test_report_has_all_sections_when_data_present():
    from src.reports import render_arabic_report
    md = render_arabic_report(_minimal_result())
    for section in ["تقرير البحث", "الإجابة", "استعلامات البحث",
                    "النتائج المُرتَّبة", "الزيارات والتحاليل",
                    "المصادر"]:
        assert section in md, f"missing section: {section!r}"


@pytest.mark.unit
def test_report_skips_research_block_when_absent():
    from src.reports import render_arabic_report
    minimal = {
        "task_id": "x", "goal": "g", "success": True, "confidence": 0.5,
        "reason": "", "summary": "hello", "steps": [], "plan": {},
        "extractions": [], "artifacts_dir": "",
    }
    md = render_arabic_report(minimal)
    assert "تقرير البحث" in md       # header still present
    assert "hello" in md             # summary still rendered
    assert "استعلامات البحث" not in md  # research-only section dropped


@pytest.mark.unit
def test_report_tolerates_missing_fields():
    from src.reports import render_arabic_report
    # Just an empty dict — should not raise.
    md = render_arabic_report({})
    assert isinstance(md, str) and len(md) > 0


@pytest.mark.unit
def test_report_ranks_candidates_by_final_score():
    from src.reports import render_arabic_report
    data = _minimal_result()
    md = render_arabic_report(data)
    # dealapp must appear before dell in the ranked table.
    pos_deal = md.find("dealapp.sa")
    pos_dell = md.find("dell.com")
    assert pos_deal != -1 and pos_dell != -1
    assert pos_deal < pos_dell


@pytest.mark.unit
def test_report_inline_safe_escapes_pipes():
    from src.reports.markdown_report import _inline_safe
    assert _inline_safe("a | b") == "a \\| b"
    assert _inline_safe("with\nnewline") == "with newline"
    assert _inline_safe("") == ""


@pytest.mark.unit
def test_write_arabic_report_to_disk(tmp_path: Path):
    from src.reports import write_arabic_report
    out = write_arabic_report(_minimal_result(), tmp_path)
    assert out.exists()
    assert out.name == "report.ar.md"
    content = out.read_text(encoding="utf-8")
    assert "تطبيق ديل" in content


# ── Discarded-candidates section ───────────────────────────────────────────

@pytest.mark.unit
def test_report_lists_discarded_candidates():
    from src.reports import render_arabic_report
    data = _minimal_result()
    # Add a judge_content step for a URL NOT in useful_sources.
    data["steps"] = [
        {"step": 1, "action": {"action": "goto", "url": "https://dell.com/"}, "ok": True, "note": "navigated"},
        {"step": 2, "action": {"action": "judge_content", "url": "https://dell.com/"},
         "ok": True, "note": "score=0.10 — irrelevant brand"},
    ]
    md = render_arabic_report(data)
    assert "مرشّحون مُستبعَدون" in md
    assert "dell.com" in md


# ── Steps log ──────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_report_renders_steps_log_collapsed():
    from src.reports import render_arabic_report
    data = _minimal_result()
    data["steps"] = [
        {"step": 1, "action": {"action": "goto", "url": "https://x.com/"}, "ok": True, "note": "ok"},
    ]
    md = render_arabic_report(data)
    assert "<details>" in md
    assert "سجل خطوات الوكيل" in md


# ── temp_signup helpers (file ledger logic, no browser) ────────────────────

@pytest.mark.unit
def test_temp_signup_slugify():
    from src.skills.temp_signup import _slug_for
    assert _slug_for("https://Example.COM/abc") == "example_com"
    assert _slug_for("https://x.io") == "x_io"
    assert _slug_for("") in ("site", "")  # graceful when no host


@pytest.mark.unit
def test_temp_signup_strong_password_has_all_classes():
    from src.skills.temp_signup import _strong_password
    import re
    p = _strong_password(20)
    assert len(p) >= 16
    assert re.search(r"[A-Z]", p) and re.search(r"[a-z]", p)
    assert re.search(r"\d", p)


@pytest.mark.unit
def test_accounts_list_and_forget(tmp_path: Path, monkeypatch):
    """The ledger functions read/write under settings.output_path/accounts."""
    from src import config as _config
    monkeypatch.setattr(_config.settings, "output_dir", str(tmp_path))
    # invalidate the cached output_path property by clearing _output_path attrs
    # — settings.output_path is a property that resolves at call time.
    from src.skills.temp_signup import list_accounts, forget_account
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    (accounts_dir / "myslug.json").write_text(
        json.dumps({"profile_name": "myslug", "site_url": "https://x.io",
                    "email": "a@b.c", "verified": True, "created_at": 0}),
        encoding="utf-8",
    )
    items = list_accounts()
    assert any(i.get("profile_name") == "myslug" for i in items)
    assert forget_account("myslug")
    assert not any(i.get("profile_name") == "myslug" for i in list_accounts())


# ── find_components helpers ────────────────────────────────────────────────

@pytest.mark.unit
def test_find_components_query_expansion_adds_libraries():
    from src.skills.find_components import _query_expansion
    qs = _query_expansion("navbar")
    assert qs[0] == "navbar"
    joined = " ".join(qs).lower()
    assert "tailwind" in joined or "bootstrap" in joined


@pytest.mark.unit
def test_find_components_query_expansion_respects_named_library():
    from src.skills.find_components import _query_expansion
    qs = _query_expansion("tailwind navbar")
    # User named tailwind → we should NOT re-add bootstrap variants.
    assert all("bootstrap" not in q.lower() for q in qs)


@pytest.mark.unit
def test_find_components_slugify_keeps_arabic():
    from src.skills.find_components import _slugify
    s = _slugify("مكوّنات tailwind")
    # Should not collapse to empty, and not raise.
    assert s and len(s) > 0


# _escape_html moved out of find_components — superseded by
# the viewer's _json_for_script + html.escape combo, covered in
# tests/unit/test_component_viewer.py::test_viewer_escapes_html_in_query_but_keeps_json_literal_safe


# ── design_tokens helpers ──────────────────────────────────────────────────

@pytest.mark.unit
def test_design_tokens_top_n_by_area_sorts_and_normalizes():
    from src.skills.design_tokens import _top_n_by_area
    bag = {"#ff0000": 100, "#00ff00": 300, "#0000ff": 50}
    out = _top_n_by_area(bag, n=2)
    assert out[0]["hex"] == "#00ff00"
    assert out[1]["hex"] == "#ff0000"
    # Ratios sum within the top-N reflect the proportions
    assert 0.6 <= out[0]["ratio"] <= 0.7  # 300/450


@pytest.mark.unit
def test_design_tokens_hex_to_rgb():
    from src.skills.design_tokens import _hex_to_rgb
    assert _hex_to_rgb("#ff0000") == (255, 0, 0)
    assert _hex_to_rgb("00ff00") == (0, 255, 0)
