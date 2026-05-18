"""Arabic Markdown report writer for research/run tasks.

Why a custom writer (instead of just dumping JSON):
  * The CLI/UI used to print TaskResult.to_dict() through json.dumps,
    which for Arabic content rendered as one long noisy blob — no
    sections, mixed bracket noise, no source list, no scores.
  * The web UI didn't enforce RTL so mixed Arabic/Latin text wrapped
    incorrectly.

This module produces a *structured* Markdown document in Arabic that
opens cleanly in any Markdown viewer (terminal `rich`, the web UI's
marked.js renderer, GitHub, Obsidian, etc.). It has stable section
headers, a metadata header, ranked source cards, per-page critiques,
and a citations block.

The output is intentionally pure data-to-text — no LLM call. Anything
the LLM produced (final answer, citations, useful facts) is already on
the TaskResult; this module just lays it out.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Public API ───────────────────────────────────────────────────────────────

def render_arabic_report(result: dict[str, Any]) -> str:
    """Return the full Arabic Markdown report as a string.

    `result` is the dict produced by `TaskResult.to_dict()`. Tolerates
    missing fields — anything absent is silently skipped so legacy
    non-research tasks still render.
    """
    parts: list[str] = []
    parts.append(_render_header(result))
    parts.append(_render_summary(result))

    research = _get_research_block(result)
    if research:
        parts.append(_render_queries(research))
        parts.append(_render_ranked_candidates(research))
        parts.append(_render_visits(result, research))
        parts.append(_render_citations(research))

    parts.append(_render_steps(result))
    parts.append(_render_footer(result))

    # Drop any empty sections so the doc stays tight.
    return "\n\n".join(p for p in parts if p and p.strip())


def write_arabic_report(result: dict[str, Any], out_dir: Path | str) -> Path:
    """Write the Arabic report to `<out_dir>/report.ar.md` and return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.ar.md"
    path.write_text(render_arabic_report(result), encoding="utf-8")
    return path


# ── Section renderers ───────────────────────────────────────────────────────

def _render_header(result: dict[str, Any]) -> str:
    goal = (result.get("goal") or "").strip()
    task_id = result.get("task_id") or ""
    success = bool(result.get("success"))
    confidence = _to_float(result.get("confidence"), 0.0)
    reason = (result.get("reason") or "").strip()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_emoji = "✅" if success else "⚠️"
    status_word = "نجاح" if success else "غير مكتمل"

    lines = [
        "<div dir=\"rtl\" lang=\"ar\" align=\"right\">",
        "",
        f"# {status_emoji} تقرير البحث",
        "",
        f"**الهدف:** {goal or '(غير محدد)'}",
        "",
        "| الحقل | القيمة |",
        "|------|--------|",
        f"| الحالة | {status_word} |",
        f"| الثقة | {confidence:.0%} |",
        f"| مُعرّف المهمة | `{task_id}` |",
        f"| تاريخ التشغيل | {ts} |",
    ]
    if reason:
        lines.append(f"| ملاحظة المُحقّق | {_inline_safe(reason)} |")
    lines.append("")
    lines.append("</div>")
    return "\n".join(lines)


def _render_summary(result: dict[str, Any]) -> str:
    summary = (result.get("summary") or "").strip()
    research = _get_research_block(result)
    synth = (research or {}).get("synthesis") or {}
    caveats = (synth.get("caveats") or "").strip()
    feedback = (synth.get("feedback") or "").strip()

    body = summary or "_(لا تتوفر إجابة نهائية)_"

    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "## 📝 الإجابة",
        "",
        body,
    ]
    if caveats:
        lines += ["", f"> **تحفّظات:** {caveats}"]
    if feedback:
        lines += ["", f"> **مراجعة ذاتية:** {feedback}"]
    lines += ["", "</div>"]
    return "\n".join(lines)


def _render_queries(research: dict[str, Any]) -> str:
    queries = research.get("queries") or []
    if not queries:
        return ""
    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "## 🔎 استعلامات البحث",
        "",
        "تم توليد الاستعلامات التالية لتغطية الهدف من زوايا متعددة:",
        "",
    ]
    for i, q in enumerate(queries, 1):
        lines.append(f"{i}. `{_inline_safe(q)}`")
    lines += ["", "</div>"]
    return "\n".join(lines)


def _render_ranked_candidates(research: dict[str, Any]) -> str:
    candidates = research.get("candidates_seen") or []
    if not candidates:
        return ""
    # Sort defensively in case caller mutated order.
    cands = sorted(candidates, key=lambda c: _to_float(c.get("final_score"), 0.0), reverse=True)
    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "## 🏆 النتائج المُرتَّبة",
        "",
        "تم ترتيب النتائج الخام بمزج بين الإشارات الحتمية (تطابق الكلمات، شكل الرابط) وتقييم نموذج اللغة:",
        "",
        "| # | الموقع | الدرجة الحتمية | درجة الذكاء | الدرجة النهائية | السبب |",
        "|---|--------|----------------|--------------|-----------------|-------|",
    ]
    for i, c in enumerate(cands[:10], 1):
        host = _inline_safe((c.get("host") or "") or _host_of(c.get("url") or ""))
        h = _to_float(c.get("heuristic_score"), 0.0)
        l = _to_float(c.get("llm_score"), 0.0)
        f = _to_float(c.get("final_score"), 0.0)
        reason = _inline_safe((c.get("llm_reason") or "")[:120])
        url = c.get("url") or ""
        host_md = f"[{host}]({url})" if url else host
        lines.append(f"| {i} | {host_md} | {h:.2f} | {l:.2f} | **{f:.2f}** | {reason} |")
    lines += ["", "</div>"]
    return "\n".join(lines)


def _render_visits(result: dict[str, Any], research: dict[str, Any]) -> str:
    """Per-visit breakdown: URL, content-critic verdict, useful facts."""
    useful = research.get("useful_sources") or []
    steps = result.get("steps") or []

    # Build a per-URL judgement map from steps (judge_content rows).
    judged: dict[str, dict[str, Any]] = {}
    for s in steps:
        act = s.get("action") or {}
        if act.get("action") == "judge_content":
            url = act.get("url") or ""
            if url:
                judged[url] = s

    if not useful and not judged:
        return ""

    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "## 🔬 الزيارات والتحاليل",
        "",
        "تم زيارة كل مرشّح وقراءة محتواه ثم تقييمه:",
        "",
    ]

    # Useful sources first (full detail), then judged-but-discarded ones.
    useful_urls = {s.get("url") for s in useful}

    for i, s in enumerate(useful, 1):
        url = s.get("url") or ""
        title = (s.get("title") or "").strip()
        verdict = (s.get("verdict") or "").strip()
        score = _to_float(s.get("score"), 0.0)
        facts = s.get("useful_facts") or []
        lines.append(f"### {i}. ✅ [{_inline_safe(title or _host_of(url) or url)}]({url})")
        lines.append("")
        lines.append(f"- **درجة الملاءمة:** {score:.0%}")
        if verdict:
            lines.append(f"- **حكم الناقد:** {_inline_safe(verdict)}")
        if facts:
            lines.append("- **الحقائق المفيدة:**")
            for f in facts[:8]:
                lines.append(f"  - {_inline_safe(str(f))}")
        lines.append("")

    # Now the ones that failed the critic.
    discarded = [
        (url, st) for url, st in judged.items()
        if url and url not in useful_urls
    ]
    if discarded:
        lines.append("### مرشّحون مُستبعَدون")
        lines.append("")
        for url, st in discarded:
            note = (st.get("note") or "").strip()
            lines.append(f"- ❌ [{_host_of(url)}]({url}) — {_inline_safe(note[:160])}")
        lines.append("")

    lines.append("</div>")
    return "\n".join(lines)


def _render_citations(research: dict[str, Any]) -> str:
    synth = (research or {}).get("synthesis") or {}
    citations = synth.get("citations") or []
    if not citations:
        return ""
    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "## 📚 المصادر",
        "",
    ]
    for c in citations:
        url = c.get("url") or ""
        quote = (c.get("quote") or "").strip()
        if quote:
            lines.append(f"- [{_host_of(url) or url}]({url}) — _{_inline_safe(quote[:280])}_")
        else:
            lines.append(f"- [{_host_of(url) or url}]({url})")
    lines += ["", "</div>"]
    return "\n".join(lines)


def _render_steps(result: dict[str, Any]) -> str:
    """Compact action log — collapsed by default so it doesn't dominate."""
    steps = result.get("steps") or []
    if not steps:
        return ""
    lines = [
        "<div dir=\"auto\" lang=\"ar\">",
        "",
        "<details>",
        "<summary>🪜 <strong>سجل خطوات الوكيل</strong> (انقر للتوسعة)</summary>",
        "",
        "| # | الإجراء | الحالة | ملاحظة |",
        "|---|---------|--------|--------|",
    ]
    for s in steps[:40]:
        n = s.get("step", "")
        act = s.get("action") or {}
        ok = "✅" if s.get("ok") else "❌"
        action_str = _summarize_action(act)
        note = _inline_safe((s.get("note") or "")[:140])
        lines.append(f"| {n} | `{action_str}` | {ok} | {note} |")
    lines += ["", "</details>", "", "</div>"]
    return "\n".join(lines)


def _render_footer(result: dict[str, Any]) -> str:
    artifacts = result.get("artifacts_dir") or ""
    if not artifacts:
        return ""
    return (
        "<div dir=\"auto\" lang=\"ar\">\n\n"
        "---\n\n"
        f"_المرفقات (صور الشاشة، JSON الكامل):_ `{artifacts}`\n\n"
        "</div>"
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_research_block(result: dict[str, Any]) -> dict[str, Any] | None:
    plan = result.get("plan") or {}
    research = plan.get("research") if isinstance(plan, dict) else None
    return research if isinstance(research, dict) else None


def _summarize_action(action: dict[str, Any]) -> str:
    a = action.get("action") or ""
    if a == "goto":
        return f"goto {_host_of(action.get('url') or '')}"
    if a == "judge_content":
        return f"judge {_host_of(action.get('url') or '')}"
    if a == "search_web":
        return f"search '{(action.get('query') or '')[:40]}'"
    if a == "click":
        return f"click #{action.get('index')}"
    if a == "type":
        return f"type #{action.get('index')}"
    return a or "?"


def _host_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return url


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _inline_safe(s: str) -> str:
    """Escape Markdown-breaking chars for inline contexts (table cells)."""
    if not s:
        return ""
    # Newlines / pipes break tables; backslash escapes work in GFM.
    return (
        s.replace("\\", "\\\\")
         .replace("|", "\\|")
         .replace("\n", " ")
         .replace("\r", " ")
         .strip()
    )
