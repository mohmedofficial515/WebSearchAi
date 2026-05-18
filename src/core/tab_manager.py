"""Multi-tab manager for Playwright browser sessions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from .browser import BrowserSession


@dataclass
class TabInfo:
    tab_id: str
    page: Any  # playwright Page


class TabManager:
    """Manages multiple browser tabs within a single BrowserContext.

    Switching tabs transparently updates session.page so all existing
    Executor/Perception code works without modification.
    """

    def __init__(self, session: BrowserSession):
        self._session = session
        self._tabs: dict[str, TabInfo] = {}
        self._counter = 0
        # Register the initial tab
        initial_id = self._next_id()
        self._tabs[initial_id] = TabInfo(tab_id=initial_id, page=session.page)
        self._current: str = initial_id

    def _next_id(self) -> str:
        tab_id = f"tab_{self._counter}"
        self._counter += 1
        return tab_id

    @property
    def current_tab_id(self) -> str:
        return self._current

    async def open_tab(self, url: str = "about:blank") -> str:
        """Open a new tab and switch to it. Returns the new tab_id."""
        assert self._session._context is not None, "BrowserSession not started"
        new_page = await self._session._context.new_page()
        tab_id = self._next_id()
        self._tabs[tab_id] = TabInfo(tab_id=tab_id, page=new_page)
        await self._switch_to(tab_id)
        if url and url != "about:blank":
            await self._session.goto(url)
        return tab_id

    async def switch_tab(self, tab_id: str) -> None:
        """Switch active tab by ID. Updates session.page."""
        if tab_id not in self._tabs:
            raise KeyError(f"Tab '{tab_id}' not found. Open tabs: {list(self._tabs.keys())}")
        await self._switch_to(tab_id)

    async def _switch_to(self, tab_id: str) -> None:
        info = self._tabs[tab_id]
        self._session.page = info.page
        self._current = tab_id
        try:
            await info.page.bring_to_front()
        except Exception:
            pass

    async def close_tab(self, tab_id: str | None = None) -> None:
        """Close a tab (defaults to current tab). Switches to previous if current."""
        target = tab_id or self._current
        if target not in self._tabs:
            return
        if len(self._tabs) == 1:
            raise RuntimeError("Cannot close the last remaining tab")
        page = self._tabs[target].page
        del self._tabs[target]
        try:
            await page.close()
        except Exception:
            pass
        if self._current == target:
            # Switch to the most recently opened remaining tab
            last_id = list(self._tabs.keys())[-1]
            await self._switch_to(last_id)

    async def list_tabs(self) -> list[dict]:
        """Return info about all open tabs."""
        result = []
        for tab_id, info in self._tabs.items():
            try:
                url = info.page.url
                title = await info.page.title()
            except Exception:
                url = "unknown"
                title = "unknown"
            result.append({
                "id": tab_id,
                "url": url,
                "title": title,
                "active": tab_id == self._current,
            })
        return result
