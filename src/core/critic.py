"""LLM-judge primitives for the search-first agent loop.

The Critic is a thin, pure-LLM layer with no browser/network deps. It
exists so the agent can ask "is this result relevant?", "does this page
answer the goal?", "should we search again?" — each as one well-scoped
LLM call returning a JSON verdict the orchestrator can act on.

Keep the prompts terse: the cheapest models in our failover chain
(groq llama-3.1-8b, gemini-flash) follow short JSON-only prompts well
and choke on essays.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .prompt_loader import load_prompt


def _rank_system(locale: str = "ar") -> str:
    return load_prompt("critic", locale=locale, section="rank")


def _content_system(locale: str = "ar") -> str:
    return load_prompt("critic", locale=locale, section="content")


def _query_system(locale: str = "ar") -> str:
    return load_prompt("critic", locale=locale, section="queries")


def _research_system(locale: str = "ar") -> str:
    return load_prompt("critic", locale=locale, section="re_search")


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ResultScore:
    index: int
    relevance: float        # 0..10
    authority: float        # 0..10
    reason: str

    def combined(self) -> float:
        # Average of the two LLM dims, normalized to 0..1.
        return ((self.relevance + self.authority) / 2.0) / 10.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentVerdict:
    score: float                    # 0..1
    verdict: str
    missing_info: str
    useful_facts: list[str]

    @property
    def is_useful(self) -> bool:
        return self.score >= 0.4 and bool(self.useful_facts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReSearchDecision:
    should_re_search: bool
    reason: str
    new_strategy: str
    new_queries: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Critic ───────────────────────────────────────────────────────────────────

class Critic:
    """Thin LLM-judge facade. One method per pure decision.

    All methods are defensive: if the LLM emits malformed JSON we fall
    back to a sensible neutral verdict rather than crashing the run.
    Search-first must NOT fail because a tiny scoring call hiccupped.
    """

    def __init__(self, llm: Any, *, locale: str = "ar") -> None:
        self._llm = llm
        self.locale = locale

    # ── Query generation ───────────────────────────────────────────────────

    async def generate_queries(self, goal: str, max_queries: int = 5) -> list[str]:
        user = f"GOAL: {goal}\n\nProduce up to {max_queries} queries."
        try:
            data = await self._llm.chat_json(_query_system(self.locale), user)
            queries = data.get("queries") if isinstance(data, dict) else None
            if isinstance(queries, list):
                clean = [str(q).strip() for q in queries if str(q).strip()]
                # Always anchor on the literal goal so we don't lose
                # the user's exact phrasing if the LLM gets creative.
                literal = goal.strip()
                if literal and (not clean or clean[0].lower() != literal.lower()):
                    clean.insert(0, literal)
                # Dedupe preserving order.
                seen: set[str] = set()
                out: list[str] = []
                for q in clean:
                    key = q.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(q)
                return out[:max_queries]
        except Exception:
            pass
        # Fallback: at least search the literal goal.
        return [goal.strip()] if goal.strip() else []

    # ── Result ranking ─────────────────────────────────────────────────────

    async def score_results(
        self,
        goal: str,
        candidates: list[dict[str, Any]],
    ) -> list[ResultScore]:
        """Score a list of {index, title, url, snippet} candidates.

        Returns a list of ResultScore — one per candidate index. If the
        LLM call fails, returns neutral 5/5 scores so ranking falls
        back to whatever heuristic the caller stacks on top.
        """
        if not candidates:
            return []
        lines = []
        for c in candidates:
            idx = c.get("index")
            title = (c.get("title") or "").strip()[:120]
            url = (c.get("url") or "").strip()[:160]
            snippet = (c.get("snippet") or "").strip()[:240]
            lines.append(f"[{idx}] {title}\n    {url}\n    {snippet}")
        user = f"GOAL: {goal}\n\nCANDIDATES:\n" + "\n\n".join(lines)
        try:
            data = await self._llm.chat_json(_rank_system(self.locale), user)
            raw = data.get("scores") if isinstance(data, dict) else None
            if isinstance(raw, list):
                out: list[ResultScore] = []
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    try:
                        out.append(ResultScore(
                            index=int(item.get("index")),
                            relevance=float(item.get("relevance") or 0),
                            authority=float(item.get("authority") or 0),
                            reason=str(item.get("reason") or "").strip(),
                        ))
                    except (TypeError, ValueError):
                        continue
                if out:
                    return out
        except Exception:
            pass
        # Fallback: neutral 5/5 across the board so the heuristic ranker decides.
        return [
            ResultScore(index=int(c.get("index", i)), relevance=5.0, authority=5.0, reason="(llm scoring unavailable)")
            for i, c in enumerate(candidates)
        ]

    # ── Page-content judging ───────────────────────────────────────────────

    async def score_content(
        self,
        goal: str,
        url: str,
        content: str,
    ) -> ContentVerdict:
        """Decide whether a fetched page actually answers the goal."""
        if not (content or "").strip():
            return ContentVerdict(
                score=0.0,
                verdict="empty content",
                missing_info="page returned no text",
                useful_facts=[],
            )
        snippet = content.strip()[:6000]
        user = f"GOAL: {goal}\n\nURL: {url}\n\nCONTENT:\n{snippet}"
        try:
            data = await self._llm.chat_json(_content_system(self.locale), user)
            if isinstance(data, dict):
                facts = data.get("useful_facts") or []
                if not isinstance(facts, list):
                    facts = []
                return ContentVerdict(
                    score=_clamp01(_to_float(data.get("score"), 0.0)),
                    verdict=str(data.get("verdict") or "").strip(),
                    missing_info=str(data.get("missing_info") or "").strip(),
                    useful_facts=[str(f).strip() for f in facts if str(f).strip()][:8],
                )
        except Exception:
            pass
        # Conservative fallback: assume mild relevance so we don't drop content silently.
        return ContentVerdict(
            score=0.4,
            verdict="(content critic unavailable — neutral score)",
            missing_info="",
            useful_facts=[],
        )

    # ── Re-search decision ─────────────────────────────────────────────────

    async def should_re_search(
        self,
        goal: str,
        queries_tried: list[str],
        urls_visited: list[str],
        useful_facts: list[str],
        why_not: str = "",
    ) -> ReSearchDecision:
        user = (
            f"GOAL: {goal}\n\n"
            f"QUERIES already tried:\n- " + "\n- ".join(queries_tried or ["(none)"]) + "\n\n"
            f"URLS visited:\n- " + "\n- ".join(urls_visited or ["(none)"]) + "\n\n"
            f"USEFUL_FACTS so far ({len(useful_facts)}):\n- " + "\n- ".join(useful_facts[:10] or ["(none)"]) + "\n\n"
            f"WHY_NOT (failures / irrelevance notes):\n{why_not or '(none)'}"
        )
        try:
            data = await self._llm.chat_json(_research_system(self.locale), user)
            if isinstance(data, dict):
                qs = data.get("new_queries") or []
                if not isinstance(qs, list):
                    qs = []
                return ReSearchDecision(
                    should_re_search=bool(data.get("should_re_search")),
                    reason=str(data.get("reason") or "").strip(),
                    new_strategy=str(data.get("new_strategy") or "").strip(),
                    new_queries=[str(q).strip() for q in qs if str(q).strip()][:5],
                )
        except Exception:
            pass
        # Conservative fallback: don't loop forever.
        return ReSearchDecision(
            should_re_search=False,
            reason="(re-search critic unavailable — stopping)",
            new_strategy="",
            new_queries=[],
        )


# ── Tiny helpers ─────────────────────────────────────────────────────────────

def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v
