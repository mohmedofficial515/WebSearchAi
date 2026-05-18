"""Unit tests for TabManager."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_page(url="https://example.com", title="Example"):
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.bring_to_front = AsyncMock()
    page.close = AsyncMock()
    return page


def _make_mock_session(page=None):
    session = MagicMock()
    session.page = page or _make_mock_page()
    session._context = MagicMock()
    session.goto = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_initial_tab_registered():
    from src.core.tab_manager import TabManager
    session = _make_mock_session()
    tm = TabManager(session)
    tabs = await tm.list_tabs()
    assert len(tabs) == 1
    assert tabs[0]["id"] == "tab_0"
    assert tabs[0]["active"] is True


@pytest.mark.asyncio
async def test_open_tab_creates_new_tab():
    from src.core.tab_manager import TabManager
    session = _make_mock_session()
    new_page = _make_mock_page(url="https://new.com", title="New")
    session._context.new_page = AsyncMock(return_value=new_page)

    tm = TabManager(session)
    tab_id = await tm.open_tab()

    assert tab_id == "tab_1"
    tabs = await tm.list_tabs()
    assert len(tabs) == 2
    assert tm.current_tab_id == "tab_1"
    assert session.page is new_page


@pytest.mark.asyncio
async def test_switch_tab_updates_session_page():
    from src.core.tab_manager import TabManager
    page1 = _make_mock_page(url="https://page1.com")
    page2 = _make_mock_page(url="https://page2.com")
    session = _make_mock_session(page=page1)
    session._context.new_page = AsyncMock(return_value=page2)

    tm = TabManager(session)
    await tm.open_tab()  # now on tab_1/page2

    await tm.switch_tab("tab_0")
    assert session.page is page1
    assert tm.current_tab_id == "tab_0"


@pytest.mark.asyncio
async def test_switch_tab_invalid_raises():
    from src.core.tab_manager import TabManager
    session = _make_mock_session()
    tm = TabManager(session)
    with pytest.raises(KeyError, match="nonexistent"):
        await tm.switch_tab("nonexistent")


@pytest.mark.asyncio
async def test_close_tab_switches_to_remaining():
    from src.core.tab_manager import TabManager
    page1 = _make_mock_page(url="https://a.com")
    page2 = _make_mock_page(url="https://b.com")
    session = _make_mock_session(page=page1)
    session._context.new_page = AsyncMock(return_value=page2)

    tm = TabManager(session)
    await tm.open_tab()  # tab_1 with page2, now active
    assert tm.current_tab_id == "tab_1"

    await tm.close_tab("tab_1")
    assert tm.current_tab_id == "tab_0"
    assert session.page is page1
    page2.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cannot_close_last_tab():
    from src.core.tab_manager import TabManager
    session = _make_mock_session()
    tm = TabManager(session)
    with pytest.raises(RuntimeError, match="Cannot close the last"):
        await tm.close_tab("tab_0")


@pytest.mark.asyncio
async def test_list_tabs_shows_all_info():
    from src.core.tab_manager import TabManager
    session = _make_mock_session(_make_mock_page("https://start.com", "Start"))
    session._context.new_page = AsyncMock(return_value=_make_mock_page("https://second.com", "Second"))

    tm = TabManager(session)
    await tm.open_tab()

    tabs = await tm.list_tabs()
    assert len(tabs) == 2
    active = [t for t in tabs if t["active"]]
    assert len(active) == 1
    assert active[0]["id"] == "tab_1"
