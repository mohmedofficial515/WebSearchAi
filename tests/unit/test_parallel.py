"""Unit tests for Phase 3 — multi-tab & parallel orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.event_bus import Event


# ── Event.to_dict carries tab_id ──────────────────────────────────────────────


@pytest.mark.unit
def test_event_to_dict_includes_tab_id_when_set():
    ev = Event(task_id="t1", type="perception", data={"step": 1}, tab_id="tab_0")
    d = ev.to_dict()
    assert d["tab_id"] == "tab_0"
    assert d["task_id"] == "t1"


@pytest.mark.unit
def test_event_to_dict_omits_tab_id_when_none():
    ev = Event(task_id="t1", type="plan", data={})
    d = ev.to_dict()
    assert "tab_id" not in d


# ── Planner schema includes tab actions ───────────────────────────────────────


@pytest.mark.unit
def test_planner_action_schema_has_tab_actions():
    # Prompts moved to prompts/decider.md in Phase B; load via the function.
    from src.core.planner import _system_decider
    decider = _system_decider("ar")
    assert "open_tab" in decider
    assert "switch_tab" in decider
    assert "close_tab" in decider
    assert "list_tabs" in decider


@pytest.mark.unit
def test_planner_decider_prompt_mentions_tabs():
    from src.core.planner import _system_decider
    assert "open_tab" in _system_decider("ar")


# ── Executor tab actions ──────────────────────────────────────────────────────


@pytest.mark.unit
async def test_executor_open_tab_no_tab_manager():
    from src.core.executor import Executor
    session = MagicMock()
    ex = Executor(session, tab_manager=None)
    result = await ex.run({"action": "open_tab", "url": "https://example.com"})
    assert result.ok is False
    assert "TabManager" in result.note


@pytest.mark.unit
async def test_executor_open_tab_with_tab_manager():
    from src.core.executor import Executor
    session = MagicMock()
    tab_manager = MagicMock()
    tab_manager.open_tab = AsyncMock(return_value="tab_1")
    ex = Executor(session, tab_manager=tab_manager)
    result = await ex.run({"action": "open_tab", "url": "https://example.com"})
    assert result.ok is True
    assert "tab_1" in result.note
    tab_manager.open_tab.assert_awaited_once_with("https://example.com")


@pytest.mark.unit
async def test_executor_switch_tab():
    from src.core.executor import Executor
    session = MagicMock()
    tab_manager = MagicMock()
    tab_manager.switch_tab = AsyncMock()
    ex = Executor(session, tab_manager=tab_manager)
    result = await ex.run({"action": "switch_tab", "tab_id": "tab_2"})
    assert result.ok is True
    tab_manager.switch_tab.assert_awaited_once_with("tab_2")


@pytest.mark.unit
async def test_executor_close_tab():
    from src.core.executor import Executor
    session = MagicMock()
    tab_manager = MagicMock()
    tab_manager.close_tab = AsyncMock()
    ex = Executor(session, tab_manager=tab_manager)
    result = await ex.run({"action": "close_tab", "tab_id": "tab_1"})
    assert result.ok is True
    tab_manager.close_tab.assert_awaited_once_with("tab_1")


@pytest.mark.unit
async def test_executor_list_tabs():
    from src.core.executor import Executor
    import json
    session = MagicMock()
    tab_manager = MagicMock()
    tabs_data = [{"id": "tab_0", "url": "https://a.com", "title": "A", "active": True}]
    tab_manager.list_tabs = AsyncMock(return_value=tabs_data)
    ex = Executor(session, tab_manager=tab_manager)
    result = await ex.run({"action": "list_tabs"})
    assert result.ok is True
    assert json.loads(result.extracted) == tabs_data


# ── Agent.run_parallel ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_run_parallel_returns_results_for_each_goal():
    """run_parallel should return one TaskResult per goal."""
    from src.core.agent import Agent, TaskResult

    fake_result = TaskResult(
        task_id="t1", goal="goal", success=True,
        confidence=0.9, reason="ok", summary="done",
    )

    with patch("src.core.agent.Agent.__aenter__", AsyncMock(return_value=MagicMock())), \
         patch("src.core.agent.Agent.__aexit__", AsyncMock(return_value=False)), \
         patch("src.core.agent.Agent.run", AsyncMock(return_value=fake_result)), \
         patch("src.core.agent.get_provider", MagicMock()), \
         patch("src.core.agent.BrowserSession", MagicMock()), \
         patch("src.core.agent.bus.publish", AsyncMock()):
        agent = MagicMock()
        agent.session = MagicMock()
        agent.session.headless = True
        agent.use_vision = False
        agent._emit = AsyncMock()
        agent.run_parallel = Agent.run_parallel.__get__(agent)

        with patch("src.core.agent.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.run = AsyncMock(return_value=fake_result)
            MockAgent.return_value = mock_instance

            results = await agent.run_parallel(
                ["goal A", "goal B"],
                task_id="task_xyz",
            )

    assert len(results) == 2
    assert all(isinstance(r, TaskResult) for r in results)


@pytest.mark.unit
async def test_run_parallel_handles_exceptions_gracefully():
    """If one goal raises, run_parallel still returns results for all goals."""
    from src.core.agent import Agent, TaskResult

    good_result = TaskResult(
        task_id="t1", goal="goal A", success=True,
        confidence=1.0, reason="ok", summary="done",
    )

    agent = MagicMock()
    agent.session = MagicMock()
    agent.session.headless = True
    agent.use_vision = False
    agent._emit = AsyncMock()
    agent.run_parallel = Agent.run_parallel.__get__(agent)

    call_count = 0

    async def _fake_run(goal, task_id, tab_id):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("browser crashed")
        return good_result

    with patch("src.core.agent.Agent") as MockAgent:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.run = AsyncMock(side_effect=_fake_run)
        MockAgent.return_value = mock_instance

        results = await agent.run_parallel(["goal A", "goal B"], task_id="t1")

    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is False
    assert "browser crashed" in results[1].reason


# ── API RunBody accepts parallel_goals ────────────────────────────────────────


@pytest.mark.unit
def test_run_body_parallel_goals_field():
    from src.api.main import RunBody
    body = RunBody(parallel_goals=["goal A", "goal B"])
    assert body.parallel_goals == ["goal A", "goal B"]
    assert body.goal == ""


@pytest.mark.unit
def test_run_body_single_goal_still_works():
    from src.api.main import RunBody
    body = RunBody(goal="do something")
    assert body.goal == "do something"
    assert body.parallel_goals == []
