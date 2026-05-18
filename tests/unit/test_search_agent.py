"""Unit tests for the search-first agentic pipeline.

These tests stub the LLM (FakeLLM) and the search backend so they run
fully offline. They lock in the contracts the orchestrator depends on:

  * query generation preserves the goal's language and always anchors
    on the literal goal,
  * ranking blends heuristic + LLM scores in the right proportions,
  * dead/duplicate hosts get filtered/diversified,
  * the content critic correctly classifies useful vs useless content,
  * the re-search decision honours the LLM verdict,
  * synthesis falls back gracefully when the LLM hiccups.
"""
from __future__ import annotations

import pytest

from tests.conftest import FakeLLM


# ── Critic ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_query_generator_preserves_arabic_and_anchors_literal():
    from src.core.critic import Critic

    fake = FakeLLM(responses=[{"queries": ["ديل عقارات السعودية", "Deal Real Estate Saudi"]}])
    critic = Critic(llm=fake)  # type: ignore[arg-type]

    qs = await critic.generate_queries("تطبيق ديل للعقارات السعودية", max_queries=5)

    # Literal goal must always lead the list (anchor).
    assert qs[0] == "تطبيق ديل للعقارات السعودية"
    # LLM-suggested queries should follow.
    assert "ديل عقارات السعودية" in qs
    # Should NOT contain transliterations not in the original LLM output.
    assert all("Dell" not in q for q in qs)


@pytest.mark.unit
async def test_query_generator_fallback_when_llm_fails():
    from src.core.critic import Critic

    # FakeLLM returns empty {} → no "queries" key → Critic falls back.
    fake = FakeLLM(responses=[{}])
    critic = Critic(llm=fake)  # type: ignore[arg-type]

    qs = await critic.generate_queries("best Python ORM 2026")
    assert qs == ["best Python ORM 2026"]


@pytest.mark.unit
async def test_score_results_neutral_on_llm_failure():
    from src.core.critic import Critic

    fake = FakeLLM(responses=[{"unexpected": "shape"}])
    critic = Critic(llm=fake)  # type: ignore[arg-type]

    candidates = [
        {"index": 0, "title": "Foo", "url": "https://a.com", "snippet": "x"},
        {"index": 1, "title": "Bar", "url": "https://b.com", "snippet": "y"},
    ]
    scores = await critic.score_results("a goal", candidates)
    assert len(scores) == 2
    assert all(s.relevance == 5.0 and s.authority == 5.0 for s in scores)


@pytest.mark.unit
async def test_score_content_classifies_useful_vs_useless():
    from src.core.critic import Critic

    # First call: useful page. Second: irrelevant.
    fake = FakeLLM(responses=[
        {
            "score": 0.85,
            "verdict": "answers the question",
            "missing_info": "",
            "useful_facts": ["Fact A", "Fact B"],
        },
        {
            "score": 0.1,
            "verdict": "unrelated",
            "missing_info": "everything",
            "useful_facts": [],
        },
    ])
    critic = Critic(llm=fake)  # type: ignore[arg-type]

    good = await critic.score_content("g", "https://a.com", "long content " * 50)
    bad = await critic.score_content("g", "https://b.com", "long content " * 50)

    assert good.is_useful
    assert good.score == 0.85
    assert good.useful_facts == ["Fact A", "Fact B"]

    assert not bad.is_useful
    assert bad.score == 0.1


@pytest.mark.unit
async def test_score_content_empty_input_returns_zero():
    from src.core.critic import Critic

    critic = Critic(llm=FakeLLM())  # type: ignore[arg-type]
    v = await critic.score_content("g", "https://a.com", "")
    assert v.score == 0.0
    assert not v.is_useful


@pytest.mark.unit
async def test_should_re_search_honours_llm_verdict():
    from src.core.critic import Critic

    fake = FakeLLM(responses=[{
        "should_re_search": True,
        "reason": "no useful pages found",
        "new_strategy": "broaden the terms",
        "new_queries": ["broader q1", "broader q2"],
    }])
    critic = Critic(llm=fake)  # type: ignore[arg-type]

    d = await critic.should_re_search(
        goal="g",
        queries_tried=["narrow"],
        urls_visited=["https://a.com"],
        useful_facts=[],
        why_not="nothing matched",
    )
    assert d.should_re_search is True
    assert d.new_queries == ["broader q1", "broader q2"]


# ── Synthesizer ─────────────────────────────────────────────────────────────

@pytest.mark.unit
async def test_synthesizer_produces_cited_answer():
    from src.core.synthesis import Synthesizer

    fake = FakeLLM(responses=[
        # Draft
        {
            "answer": "The answer is X.",
            "citations": [{"url": "https://a.com", "quote": "supporting quote"}],
            "confidence": 0.8,
            "caveats": "",
        },
        # Critique
        {
            "addresses_goal": True,
            "well_cited": True,
            "final_confidence": 0.85,
            "feedback": "looks good",
        },
    ])
    s = Synthesizer(llm=fake)  # type: ignore[arg-type]

    out = await s.synthesize("what is X?", [{
        "url": "https://a.com",
        "verdict": "answers it",
        "useful_facts": ["X is real"],
    }])
    assert out.answer == "The answer is X."
    assert len(out.citations) == 1
    assert out.citations[0].url == "https://a.com"
    assert out.confidence == 0.85
    assert out.addresses_goal is True


@pytest.mark.unit
async def test_synthesizer_empty_sources_returns_low_confidence():
    from src.core.synthesis import Synthesizer

    s = Synthesizer(llm=FakeLLM())  # type: ignore[arg-type]
    out = await s.synthesize("goal", [])
    assert out.answer == ""
    assert out.confidence == 0.0
    assert out.addresses_goal is False


@pytest.mark.unit
async def test_synthesizer_fallback_when_draft_missing():
    from src.core.synthesis import Synthesizer

    # Draft returns no "answer" key → synthesizer should build a tiny
    # fallback from the useful_facts rather than return empty.
    fake = FakeLLM(responses=[{}, {}])  # draft and critique both empty
    s = Synthesizer(llm=fake)  # type: ignore[arg-type]
    out = await s.synthesize("g", [{
        "url": "https://a.com",
        "verdict": "ok",
        "useful_facts": ["Fact one"],
    }])
    assert "Fact one" in out.answer
    assert out.confidence > 0  # at least the fallback floor


# ── Heuristic ranker ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_heuristic_score_prefers_token_overlap():
    from src.core.search_agent import _heuristic_score

    items = [
        {"title": "Real estate Saudi 2026 trends", "snippet": "best property", "url": "https://reasr.example/page"},
        {"title": "Cooking recipes", "snippet": "pasta", "url": "https://food.example/pasta"},
    ]
    scores = _heuristic_score("real estate Saudi", ["real estate Saudi 2026"], items)
    assert scores[0] > scores[1]


@pytest.mark.unit
def test_heuristic_score_penalizes_shorteners_and_aggregators():
    from src.core.search_agent import _heuristic_score

    items = [
        {"title": "x", "snippet": "real estate Saudi", "url": "https://bit.ly/abc"},
        {"title": "x", "snippet": "real estate Saudi", "url": "https://example.sa/properties"},
    ]
    scores = _heuristic_score("real estate Saudi", [], items)
    assert scores[1] > scores[0]


@pytest.mark.unit
def test_pick_diverse_caps_one_per_host():
    from src.core.search_agent import RankedCandidate, _pick_diverse

    cands = [
        RankedCandidate(url="https://a.com/1", title="a1", snippet="", source="x",
                        queries_matched=[], heuristic_score=0.9, llm_score=0.9,
                        final_score=0.9, llm_reason="", host="a.com"),
        RankedCandidate(url="https://a.com/2", title="a2", snippet="", source="x",
                        queries_matched=[], heuristic_score=0.8, llm_score=0.8,
                        final_score=0.8, llm_reason="", host="a.com"),
        RankedCandidate(url="https://b.com/1", title="b1", snippet="", source="x",
                        queries_matched=[], heuristic_score=0.7, llm_score=0.7,
                        final_score=0.7, llm_reason="", host="b.com"),
    ]
    chosen = _pick_diverse(cands, 2)
    hosts = {c.host for c in chosen}
    assert hosts == {"a.com", "b.com"}


@pytest.mark.unit
def test_dedupe_key_strips_query_and_trailing_slash():
    from src.core.search_agent import _dedupe_key

    assert _dedupe_key("https://www.A.com/path?x=1") == _dedupe_key("https://a.com/path/")
    assert _dedupe_key("https://x.com") == "x.com/"


# ── SearchAgent (full pipeline with mocked search) ──────────────────────────

@pytest.mark.unit
async def test_search_agent_research_full_flow(monkeypatch):
    """End-to-end orchestrator test: mocked search backend + mocked LLM."""
    from src.core import search_agent as sa_mod
    from src.core.search_agent import SearchAgent
    from src.search.backends import SearchResult

    # Stub the search() coroutine the orchestrator calls.
    fake_results = {
        "تطبيق ديل للعقارات السعودية": [
            SearchResult(title="Deal app — Saudi real estate", url="https://dealapp.sa/",
                         snippet="تطبيق ديل للعقارات في السعودية", source="ddgs"),
            SearchResult(title="Dell laptops", url="https://dell.com/",
                         snippet="dell computers", source="ddgs"),
        ],
        "ديل عقارات": [
            SearchResult(title="Bayut KSA", url="https://bayut.sa/", snippet="عقارات", source="ddgs"),
        ],
    }

    async def _fake_search(q, max_results=None):
        return fake_results.get(q, [])

    monkeypatch.setattr(sa_mod, "api_search", _fake_search)

    # FakeLLM responses, in order: generate_queries → score_results.
    fake = FakeLLM(responses=[
        {"queries": ["ديل عقارات"]},  # generator
        # score_results: index→relevance/authority
        {"scores": [
            {"index": 0, "relevance": 9, "authority": 8, "reason": "matches Saudi real estate"},
            {"index": 1, "relevance": 1, "authority": 2, "reason": "wrong brand"},
            {"index": 2, "relevance": 7, "authority": 8, "reason": "real estate authority"},
        ]},
    ])
    agent = SearchAgent(llm=fake)  # type: ignore[arg-type]

    research = await agent.research("تطبيق ديل للعقارات السعودية", max_candidates=2)

    assert "تطبيق ديل للعقارات السعودية" in research.queries
    assert "ديل عقارات" in research.queries
    assert len(research.all_results) == 3
    # The dealapp.sa result must outrank dell.com.
    urls_in_order = [c.url for c in research.candidates]
    assert urls_in_order.index("https://dealapp.sa/") < urls_in_order.index("https://dell.com/")
    # Visit queue is diversified and within max_candidates.
    assert len(research.visit_queue) <= 2
    assert "https://dealapp.sa/" in {c.url for c in research.visit_queue}


@pytest.mark.unit
async def test_search_agent_handles_zero_results(monkeypatch):
    from src.core import search_agent as sa_mod
    from src.core.search_agent import SearchAgent

    async def _empty(q, max_results=None):
        return []

    monkeypatch.setattr(sa_mod, "api_search", _empty)

    fake = FakeLLM(responses=[{"queries": ["q"]}])
    agent = SearchAgent(llm=fake)  # type: ignore[arg-type]

    research = await agent.research("nothing here")
    assert research.visit_queue == []
    assert research.candidates == []
    assert "No results" in research.notes


# ── URL detection helper ────────────────────────────────────────────────────

@pytest.mark.unit
def test_goal_url_detection():
    from src.core.agent import _goal_has_literal_url

    assert _goal_has_literal_url("summarize https://example.com/x")
    assert _goal_has_literal_url("see http://x.io for details")
    assert not _goal_has_literal_url("تطبيق ديل للعقارات السعودية")
    assert not _goal_has_literal_url("best Python ORM 2026")
    assert not _goal_has_literal_url("")
