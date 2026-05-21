"""SearchAgent — the search-first agentic research orchestrator.

This is what the user asked for: an agent that takes KEYWORDS (not a
URL), searches the web, analyzes the results, critiques the candidates,
chooses the best ones, visits them, judges their content, re-searches
if needed, and synthesizes a cited answer. Plan → search → rank →
critique → select → visit → judge → (re-search?) → synthesize.

This module owns *steps 1-4 + 6 + 8*:
    - generate diverse queries
    - run parallel searches
    - dedupe + heuristic-rank
    - LLM-critique candidates
    - decide whether to re-search
    - synthesize the final answer

It does NOT spawn or own a browser. Page-visiting (step 5) is delegated
back to the caller — typically `Agent.run()`, which already owns a
stealth `BrowserSession`. The orchestrator returns a `VisitQueue` of
ranked candidates; the caller visits them, calls back into
`SearchAgent.judge_content()`, and feeds the verdicts back in. This
keeps the orchestrator pure (testable without Playwright) and lets the
existing browser stack handle CAPTCHAs, dead URLs, and stealth.

Public surface:
    sa = SearchAgent(llm)
    research = await sa.research(goal, ...)   # generates + ranks candidates
    verdict  = await sa.judge_content(goal, url, text)
    decision = await sa.decide_re_search(goal, queries, urls, facts, why_not)
    final    = await sa.synthesize(goal, useful_sources)
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field, asdict
from collections import Counter
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from ..config import settings
from ..search import SearchResult, search as api_search
from ..archive.store import _tokens as _archive_tokens  # Arabic+English aware tokenizer
from ..utils.logger import log
from .critic import Critic, ContentVerdict, ReSearchDecision, ResultScore
from .synthesis import Synthesis, Synthesizer


# ── Result dataclasses ──────────────────────────────────────────────────────

@dataclass
class RankedCandidate:
    url: str
    title: str
    snippet: str
    source: str             # which backend produced this
    queries_matched: list[str]  # which of our queries surfaced this result
    heuristic_score: float  # 0..1
    llm_score: float        # 0..1
    final_score: float      # 0..1 weighted blend
    llm_reason: str         # critic's one-liner
    host: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchPlan:
    goal: str
    queries: list[str] = field(default_factory=list)
    all_results: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[RankedCandidate] = field(default_factory=list)
    visit_queue: list[RankedCandidate] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "queries": self.queries,
            "n_raw_results": len(self.all_results),
            "candidates": [c.to_dict() for c in self.candidates],
            "visit_queue": [c.to_dict() for c in self.visit_queue],
            "notes": self.notes,
        }


# ── Heuristic ranker ─────────────────────────────────────────────────────────
#
# We don't want LLM-only ranking — it's expensive AND can hallucinate
# authority signals. The heuristic does cheap, deterministic work first:
#   * token overlap title+snippet vs. goal+queries (TF-IDF over the
#     candidate pool, reusing the archive tokenizer for AR/EN folding)
#   * shorter URLs slightly preferred (root domain pages tend to be
#     more authoritative than deep-linked SEO chum)
#   * known spammy/aggregator/shortener domains penalized
#   * diversity penalty: cap a single domain from dominating the list
#
# These signals combine to 0..1; the orchestrator then blends with the
# LLM score using `heuristic_weight` (default 0.4).

_SHORTENER_HOSTS = {
    "bit.ly", "t.co", "goo.gl", "tinyurl.com", "is.gd", "buff.ly",
    "ow.ly", "lnkd.in", "shorturl.at", "cutt.ly",
}
_AGGREGATOR_PENALTY_HOSTS = {
    "pinterest.com", "quora.com", "answers.com", "wikihow.com",
    "ehow.com", "answers.yahoo.com",
}
# Video platforms — always excluded from research results. These links
# open video players, not text content, so they never help a researcher.
_VIDEO_HOSTS: set[str] = {
    "youtube.com", "youtu.be", "vimeo.com", "dailymotion.com",
    "twitch.tv", "tiktok.com", "bilibili.com", "rumble.com",
    "odysee.com", "loom.com", "wistia.com", "sproutvideo.com",
}


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def _tfidf_corpus_score(query_tokens: list[str], docs: list[list[str]]) -> list[float]:
    """Given a query token list and a list of per-doc token lists, return
    a cosine-TFIDF score for each doc. IDF is computed across the doc
    pool only (small corpus = fast)."""
    if not docs or not query_tokens:
        return [0.0] * len(docs)
    n = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        for w in set(d):
            df[w] += 1
    idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
    q_tf = Counter(query_tokens)
    q_weights = {w: (1 + math.log(c)) * idf.get(w, 0.0) for w, c in q_tf.items()}
    q_norm = sum(v * v for v in q_weights.values()) ** 0.5 or 1e-9
    scores: list[float] = []
    for d in docs:
        if not d:
            scores.append(0.0)
            continue
        d_tf = Counter(d)
        d_weights = {w: (1 + math.log(c)) * idf.get(w, 0.0) for w, c in d_tf.items()}
        d_norm = sum(v * v for v in d_weights.values()) ** 0.5 or 1e-9
        dot = sum(q_weights[w] * d_weights.get(w, 0.0) for w in q_weights)
        scores.append(dot / (q_norm * d_norm))
    return scores


def _heuristic_score(
    goal: str,
    queries: list[str],
    items: list[dict[str, Any]],
) -> list[float]:
    """0..1 score per item. Combines token overlap + URL-shape signals."""
    if not items:
        return []
    query_blob = goal + " " + " ".join(queries or [])
    q_tokens = _archive_tokens(query_blob)
    docs = [
        _archive_tokens(((it.get("title") or "") + " " + (it.get("snippet") or "")))
        for it in items
    ]
    overlap = _tfidf_corpus_score(q_tokens, docs)

    # Domain-shape bonuses/penalties
    out: list[float] = []
    seen_hosts: dict[str, int] = {}
    for i, it in enumerate(items):
        host = _host_of(it.get("url") or "")
        seen_hosts[host] = seen_hosts.get(host, 0) + 1
        score = overlap[i]  # already 0..~1
        if host in _SHORTENER_HOSTS:
            score *= 0.4
        elif host in _AGGREGATOR_PENALTY_HOSTS:
            score *= 0.7
        # Shallow-path bonus: bare-domain / one-segment URLs tend to be
        # the canonical landing page for a brand search.
        try:
            path = urlparse(it.get("url") or "").path or "/"
            depth = len([p for p in path.split("/") if p])
            if depth <= 1:
                score += 0.05
        except Exception:
            pass
        # Domain-diversity penalty for the 3rd+ result from same host.
        if seen_hosts[host] >= 3:
            score *= 0.6
        out.append(max(0.0, min(1.0, score)))
    return out


# ── SearchAgent ──────────────────────────────────────────────────────────────

class SearchAgent:
    """Orchestrates the search→rank→critique→select cycle.

    Stateless: every call is independent. Caller manages cross-step state
    (visited URLs, accumulated useful facts, re-search count).
    """

    def __init__(self, llm: Any, *, critic: Critic | None = None,
                 synthesizer: Synthesizer | None = None) -> None:
        self._llm = llm
        self.critic = critic or Critic(llm)
        self.synthesizer = synthesizer or Synthesizer(llm)

    # ── Stage 1-4: research (pre-visit) ────────────────────────────────────

    async def research(
        self,
        goal: str,
        *,
        max_queries: int | None = None,
        max_results_per_query: int | None = None,
        max_candidates: int | None = None,
        avoid_hosts: set[str] | None = None,
        avoid_queries: set[str] | None = None,
        seed_queries: list[str] | None = None,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> ResearchPlan:
        """Run the full pre-visit pipeline.

        Steps:
          1. generate diverse queries (Critic.generate_queries) — or use
             `seed_queries` verbatim when the caller (re-search round)
             already has critic-proposed angles. Passing seed_queries is
             how we keep `goal` pristine instead of mutating it with
             "| retry-angles: …" suffixes that bloat into a 500-char
             string by round 3 and break the SERP.
          2. parallel search across queries (asyncio.gather)
          3. dedupe by URL, attach which-queries-matched
          4. heuristic rank (TF-IDF + URL shape)
          5. LLM critique top-N (Critic.score_results)
          6. blend → final score → take top-K visit queue
        """
        n_visit = max_candidates or settings.research_max_candidates
        n_per_q = max_results_per_query or settings.search_max_results
        n_queries = max_queries or getattr(settings, "research_max_queries", 5)

        # ── 1. queries ─────────────────────────────────────────────────
        if seed_queries:
            # Caller supplied queries verbatim (typically the critic's
            # new_queries from the previous re-search round). Anchor on
            # the literal goal first so we never lose the user's exact
            # phrasing, then dedupe.
            literal = goal.strip()
            raw_seed = [literal] if literal else []
            raw_seed.extend(str(q).strip() for q in seed_queries if str(q).strip())
            seen: set[str] = set()
            queries = []
            for q in raw_seed:
                k = q.lower()
                if k not in seen:
                    seen.add(k)
                    queries.append(q)
            queries = queries[:n_queries]
        else:
            queries = await self.critic.generate_queries(goal, max_queries=n_queries)
        if avoid_queries:
            queries = [q for q in queries if q.lower() not in {a.lower() for a in avoid_queries}]
        if not queries:
            queries = [goal]
        await _emit(on_event, "queries_generated", {"queries": queries})

        # ── 2. parallel search ─────────────────────────────────────────
        async def _safe_search(q: str) -> tuple[str, list[SearchResult]]:
            try:
                rs = await api_search(q, max_results=n_per_q)
                return q, rs
            except Exception as exc:  # noqa: BLE001
                log.warning(f"search failed for {q!r}: {exc}")
                return q, []

        results_per_query = await asyncio.gather(*[_safe_search(q) for q in queries])

        # ── 3. dedupe by URL ───────────────────────────────────────────
        # Track which queries each URL came up for — diversity signal.
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for q, rs in results_per_query:
            for r in rs:
                url = (r.url or "").strip()
                if not url:
                    continue
                host = _host_of(url)
                if host in _VIDEO_HOSTS:
                    continue
                if avoid_hosts and host in avoid_hosts:
                    continue
                key = _dedupe_key(url)
                if key not in merged:
                    order.append(key)
                    merged[key] = {
                        "url": url,
                        "title": r.title,
                        "snippet": r.snippet,
                        "source": r.source,
                        "queries_matched": [q],
                        "host": host,
                    }
                else:
                    if q not in merged[key]["queries_matched"]:
                        merged[key]["queries_matched"].append(q)
                    # Prefer the longer snippet (more info for ranker).
                    if len(r.snippet or "") > len(merged[key]["snippet"] or ""):
                        merged[key]["snippet"] = r.snippet
        raw_items = [merged[k] for k in order]
        await _emit(on_event, "results_merged",
                    {"n_unique": len(raw_items), "n_queries": len(queries)})

        if not raw_items:
            return ResearchPlan(
                goal=goal, queries=queries, all_results=[], candidates=[],
                visit_queue=[],
                notes="No results from any backend.",
            )

        # ── 4. heuristic rank ──────────────────────────────────────────
        h_scores = _heuristic_score(goal, queries, raw_items)
        # Bonus: results that matched multiple queries are stronger signal.
        for i, it in enumerate(raw_items):
            n_q = len(it.get("queries_matched") or [])
            if n_q >= 2:
                h_scores[i] = min(1.0, h_scores[i] + 0.05 * (n_q - 1))

        # Keep top 10 for LLM critique (cap LLM cost).
        ranked = sorted(range(len(raw_items)), key=lambda i: h_scores[i], reverse=True)
        top_idx = ranked[:10]

        # ── 5. LLM critique on top-N ───────────────────────────────────
        critique_input = [
            {
                "index": i,
                "title": raw_items[i].get("title"),
                "url": raw_items[i].get("url"),
                "snippet": raw_items[i].get("snippet"),
            }
            for i in top_idx
        ]
        llm_scores: list[ResultScore] = await self.critic.score_results(goal, critique_input)
        llm_by_idx = {rs.index: rs for rs in llm_scores}

        # ── 6. blend → candidates ──────────────────────────────────────
        hw = float(settings.research_heuristic_weight)
        lw = 1.0 - hw
        candidates: list[RankedCandidate] = []
        for i in top_idx:
            it = raw_items[i]
            h = h_scores[i]
            ls = llm_by_idx.get(i)
            l = ls.combined() if ls else 0.5
            final = h * hw + l * lw
            candidates.append(RankedCandidate(
                url=it["url"],
                title=it.get("title") or "",
                snippet=it.get("snippet") or "",
                source=it.get("source") or "",
                queries_matched=list(it.get("queries_matched") or []),
                host=it.get("host") or "",
                heuristic_score=round(h, 4),
                llm_score=round(l, 4),
                final_score=round(final, 4),
                llm_reason=(ls.reason if ls else ""),
            ))
        candidates.sort(key=lambda c: c.final_score, reverse=True)
        # Diversity in the visit queue too: don't pick 3 results from
        # the same host if alternatives exist.
        visit_queue = _pick_diverse(candidates, n_visit)

        await _emit(on_event, "candidates_ranked", {
            "n_candidates": len(candidates),
            "visit_queue": [
                {
                    "url": c.url,
                    "title": c.title,
                    "final_score": c.final_score,
                    "heuristic_score": c.heuristic_score,
                    "llm_score": c.llm_score,
                    "reason": c.llm_reason,
                }
                for c in visit_queue
            ],
        })

        return ResearchPlan(
            goal=goal,
            queries=queries,
            all_results=raw_items,
            candidates=candidates,
            visit_queue=visit_queue,
            notes=f"{len(queries)} queries → {len(raw_items)} unique results → {len(candidates)} ranked → {len(visit_queue)} to visit",
        )

    # ── Stage 5 helper: content judging (per visited page) ─────────────────

    async def judge_content(
        self, goal: str, url: str, content: str,
    ) -> ContentVerdict:
        return await self.critic.score_content(goal, url, content)

    # ── Stage 6: re-search decision ────────────────────────────────────────

    async def decide_re_search(
        self,
        goal: str,
        queries_tried: list[str],
        urls_visited: list[str],
        useful_facts: list[str],
        why_not: str = "",
    ) -> ReSearchDecision:
        return await self.critic.should_re_search(
            goal=goal,
            queries_tried=queries_tried,
            urls_visited=urls_visited,
            useful_facts=useful_facts,
            why_not=why_not,
        )

    # ── Stage 7-8: synthesis ───────────────────────────────────────────────

    async def synthesize(
        self,
        goal: str,
        useful_sources: list[dict[str, Any]],
    ) -> Synthesis:
        return await self.synthesizer.synthesize(goal, useful_sources)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _dedupe_key(url: str) -> str:
    """Normalize a URL for dedupe: strip query/fragment, lowercase host."""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower().lstrip("www.")
        path = (p.path or "/").rstrip("/") or "/"
        return f"{host}{path}"
    except Exception:
        return url.lower()


def _pick_diverse(candidates: list[RankedCandidate], n: int) -> list[RankedCandidate]:
    """Pick top-N preferring host diversity (max 1 per host until quota,
    then fill from remainder). Keeps the visit queue from being three
    pages of the same site."""
    if n <= 0 or not candidates:
        return []
    chosen: list[RankedCandidate] = []
    used_hosts: set[str] = set()
    for c in candidates:
        if len(chosen) >= n:
            break
        if c.host and c.host in used_hosts:
            continue
        chosen.append(c)
        used_hosts.add(c.host)
    if len(chosen) < n:
        for c in candidates:
            if c in chosen:
                continue
            chosen.append(c)
            if len(chosen) >= n:
                break
    return chosen


async def _emit(
    cb: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
    type_: str,
    data: dict[str, Any],
) -> None:
    if cb is None:
        return
    try:
        await cb(type_, data)
    except Exception as exc:  # noqa: BLE001
        log.debug(f"on_event callback raised: {exc}")
