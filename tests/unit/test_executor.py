"""Executor unit tests — uses mocked BrowserSession."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _fake_session() -> MagicMock:
    """A BrowserSession double whose methods are AsyncMocks."""
    m = MagicMock()
    m.goto = AsyncMock()
    m.click = AsyncMock()
    m.type = AsyncMock()
    m.press = AsyncMock()
    m.scroll = AsyncMock()
    m.eval_js = AsyncMock(return_value="page content here")
    return m


@pytest.mark.unit
async def test_extract_returns_evidence_in_note():
    """The note must contain real extracted text, not just the 'what' param.
    This is the regression test for the loop-bug fixed in core/executor.py.
    """
    from src.core.executor import Executor

    session = _fake_session()
    session.eval_js = AsyncMock(return_value="real extracted content " * 20)

    executor = Executor(session)  # type: ignore[arg-type]
    result = await executor.run({"action": "extract", "what": "anything"})

    assert result.ok is True
    assert "extracted" in result.note
    assert "real extracted content" in result.note  # evidence, not just intent
    assert result.extracted is not None and len(result.extracted) > 100


@pytest.mark.unit
async def test_unknown_action_returns_not_ok():
    from src.core.executor import Executor

    result = await Executor(_fake_session()).run({"action": "teleport"})
    assert result.ok is False
    assert "unknown" in result.note.lower()


@pytest.mark.unit
@pytest.mark.parametrize("action_name", ["done", "fail"])
async def test_terminal_actions_succeed(action_name):
    from src.core.executor import Executor

    result = await Executor(_fake_session()).run({"action": action_name, "summary": "x"})
    assert result.ok is True
    assert action_name in result.note
