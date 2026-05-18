"""Unit tests for src/core/orchestrator.py."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.orchestrator import Orchestrator, PipelineStep


class _FakeLLM:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def chat_json(self, _system: str, _user: str) -> dict:
        return self._payload

    async def close(self) -> None:
        pass


async def _no_runner(_skill: str, _params: dict[str, Any]) -> dict[str, Any]:
    return {}


# ── is_compound_heuristic ───────────────────────────────────────────────────


def test_heuristic_detects_arabic_conjunction() -> None:
    orch = Orchestrator(llm=_FakeLLM({}), step_runner=_no_runner)
    assert orch.is_compound_heuristic("ابحث عن react ثم أنشئ تقرير عنه") is True


def test_heuristic_detects_english_then() -> None:
    orch = Orchestrator(llm=_FakeLLM({}), step_runner=_no_runner)
    assert orch.is_compound_heuristic("explore the site then clone it") is True


def test_heuristic_rejects_atomic_question() -> None:
    orch = Orchestrator(llm=_FakeLLM({}), step_runner=_no_runner)
    assert orch.is_compound_heuristic("what is react") is False
    assert orch.is_compound_heuristic("") is False


def test_heuristic_detects_multiple_clauses() -> None:
    orch = Orchestrator(llm=_FakeLLM({}), step_runner=_no_runner)
    assert orch.is_compound_heuristic("explore the site, clone its homepage") is True


# ── _resolve_params ─────────────────────────────────────────────────────────


def test_resolve_simple_ref() -> None:
    resolved, missing = Orchestrator._resolve_params(
        {"url": "$s1.url"},
        {"s1": {"url": "https://a.com"}},
    )
    assert resolved == {"url": "https://a.com"}
    assert missing == []


def test_resolve_nested_ref_with_list_index() -> None:
    resolved, _ = Orchestrator._resolve_params(
        {"url": "$s1.results.0.url"},
        {"s1": {"results": [{"url": "https://x.com"}, {"url": "https://y.com"}]}},
    )
    assert resolved == {"url": "https://x.com"}


def test_resolve_passes_literals_through() -> None:
    resolved, _ = Orchestrator._resolve_params(
        {"max_assets": 60, "headless": True},
        {},
    )
    assert resolved == {"max_assets": 60, "headless": True}


def test_resolve_detects_askuser_sentinel() -> None:
    resolved, missing = Orchestrator._resolve_params(
        {"email": "$askUser", "password": "literal"},
        {},
    )
    assert resolved == {"email": None, "password": "literal"}
    assert missing == ["email"]


def test_resolve_missing_step_returns_none() -> None:
    resolved, _ = Orchestrator._resolve_params(
        {"url": "$s99.url"},
        {},
    )
    assert resolved == {"url": None}


# ── plan() — LLM parsing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_parses_valid_pipeline() -> None:
    llm = _FakeLLM({
        "summary_ar": "بحث ثم استكشاف",
        "needs_approval": False,
        "steps": [
            {"step_id": "s1", "skill": "research", "label_ar": "بحث",
             "params": {"goal": "react"}},
            {"step_id": "s2", "skill": "explore", "label_ar": "استكشاف",
             "params": {"url": "$s1.starting_url"}},
        ],
    })
    orch = Orchestrator(llm, step_runner=_no_runner)
    pipeline = await orch.plan("ابحث عن react ثم استكشف موقعها الرسمي")
    assert len(pipeline.steps) == 2
    assert pipeline.steps[0].skill == "research"
    assert pipeline.steps[1].params["url"] == "$s1.starting_url"
    assert pipeline.summary_ar == "بحث ثم استكشاف"


@pytest.mark.asyncio
async def test_plan_falls_back_on_empty_llm_response() -> None:
    orch = Orchestrator(_FakeLLM({}), step_runner=_no_runner)
    pipeline = await orch.plan("ابحث عن شيء")
    # Degrades to single-step research pipeline
    assert len(pipeline.steps) == 1
    assert pipeline.steps[0].skill == "research"


# ── run() — happy path + paused ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_yields_plan_start_end_events() -> None:
    async def runner(skill: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "skill": skill, "params": params}

    llm = _FakeLLM({
        "summary_ar": "x",
        "needs_approval": False,
        "steps": [
            {"step_id": "s1", "skill": "research", "label_ar": "x",
             "params": {"goal": "g"}},
        ],
    })
    orch = Orchestrator(llm, step_runner=runner)
    pipeline = await orch.plan("g")
    events = [ev async for ev in orch.run(pipeline)]
    types = [e["type"] for e in events]
    assert types == [
        "pipeline_plan",
        "pipeline_step_start",
        "pipeline_step_end",
        "pipeline_end",
    ]
    assert events[-1]["data"]["ok"] is True


@pytest.mark.asyncio
async def test_run_pauses_on_askuser() -> None:
    async def runner(_skill: str, _params: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("should not have run a paused step")

    llm = _FakeLLM({
        "summary_ar": "x",
        "needs_approval": False,
        "steps": [
            {"step_id": "s1", "skill": "login", "label_ar": "تسجيل دخول",
             "params": {"email": "$askUser", "password": "$askUser"},
             "required_fields": [
                 {"name": "email", "label_ar": "البريد", "type": "email"},
                 {"name": "password", "label_ar": "كلمة المرور", "type": "password"},
             ]},
        ],
    })
    orch = Orchestrator(llm, step_runner=runner)
    pipeline = await orch.plan("سجّل دخولي")
    events = [ev async for ev in orch.run(pipeline)]
    types = [e["type"] for e in events]
    assert "pipeline_paused" in types
    paused = [e for e in events if e["type"] == "pipeline_paused"][0]
    field_names = {f["name"] for f in paused["data"]["required_fields"]}
    assert field_names == {"email", "password"}
