"""Planner unit tests with mocked LLM."""

from __future__ import annotations

import pytest

from tests.conftest import FakeLLM


@pytest.mark.unit
async def test_planner_returns_structured_plan():
    from src.core.planner import Planner

    fake = FakeLLM(responses=[
        {
            "goal": "Open httpbin",
            "success_criteria": ["JSON visible"],
            "starting_url": "https://httpbin.org/get",
            "subtasks": ["go to url", "extract"],
        }
    ])
    planner = Planner(llm=fake)  # type: ignore[arg-type]
    plan = await planner.plan("Open httpbin and read JSON")

    assert plan.starting_url == "https://httpbin.org/get"
    assert plan.subtasks == ["go to url", "extract"]
    assert plan.success_criteria == ["JSON visible"]


@pytest.mark.unit
async def test_decide_returns_action():
    from src.core.planner import Planner

    fake = FakeLLM(responses=[{"action": "goto", "url": "https://example.com"}])
    planner = Planner(llm=fake)  # type: ignore[arg-type]

    decision = await planner.decide(
        goal="visit example",
        history=[],
        snapshot_text="URL: about:blank\nElements: (none)",
    )
    assert decision["action"] == "goto"
    assert decision["url"] == "https://example.com"
