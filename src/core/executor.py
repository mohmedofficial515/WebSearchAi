"""Translate LLM-decided JSON actions into Playwright calls."""
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from .browser import BrowserSession
from .perception import Perception
from ..search import search as api_search, SearchResult


@dataclass
class ActionResult:
    ok: bool
    action: str
    note: str = ""
    extracted: str = ""


class Executor:
    def __init__(self, session: BrowserSession, tab_manager: Any = None):
        self._s = session
        self._tabs = tab_manager  # Optional TabManager

    async def run(self, action_dict: dict) -> ActionResult:
        action = action_dict.get("action", "")
        try:
            # ── Navigation ────────────────────────────────────────────────
            if action == "goto":
                url = action_dict.get("url", "")
                await self._s.goto(url)
                return ActionResult(ok=True, action=action, note=f"navigated to {url}")

            elif action == "click":
                idx = action_dict.get("index")
                sel = action_dict.get("selector") or (Perception.selector_for_index(idx) if idx is not None else "")
                await self._s.click(sel)
                return ActionResult(ok=True, action=action, note=f"clicked {sel}")

            elif action == "type":
                idx = action_dict.get("index")
                sel = action_dict.get("selector") or (Perception.selector_for_index(idx) if idx is not None else "")
                text = action_dict.get("text", "")
                await self._s.type(sel, text)
                return ActionResult(ok=True, action=action, note=f"typed into {sel}")

            elif action == "press":
                key = action_dict.get("key", "Enter")
                await self._s.press(key)
                return ActionResult(ok=True, action=action, note=f"pressed {key}")

            elif action == "scroll":
                direction = action_dict.get("direction", "down")
                amount = action_dict.get("amount", 300)
                await self._s.scroll(direction, amount)
                return ActionResult(ok=True, action=action, note=f"scrolled {direction}")

            elif action == "wait":
                ms = action_dict.get("ms", 1000)
                await asyncio.sleep(ms / 1000)
                return ActionResult(ok=True, action=action, note=f"waited {ms}ms")

            elif action == "extract":
                raw = await self._s.eval_js("document.body.innerText")
                text = str(raw or "")[:4000]
                return ActionResult(ok=True, action=action, note=text, extracted=text)

            # ── Search (API, not browser) ────────────────────────────────
            # Prefer this over scraping Bing/Google: the agent gets clean
            # JSON results without ever triggering a CAPTCHA challenge,
            # then visits the URLs it picks with the stealth browser.
            elif action == "search_web":
                query = (action_dict.get("query") or "").strip()
                if not query:
                    return ActionResult(ok=False, action=action, note="query missing")
                limit = int(action_dict.get("max_results") or 8)
                results: list[SearchResult] = await api_search(query, max_results=limit)
                payload = [r.to_dict() for r in results]
                pretty = json.dumps(payload, ensure_ascii=False, indent=2)
                return ActionResult(
                    ok=True,
                    action=action,
                    note=f"{len(results)} results for {query!r}\n{pretty}",
                    extracted=pretty,
                )

            # ── Multi-tab ─────────────────────────────────────────────────
            elif action == "open_tab":
                if self._tabs is None:
                    return ActionResult(ok=False, action=action, note="TabManager not available")
                url = action_dict.get("url", "about:blank")
                tab_id = await self._tabs.open_tab(url)
                return ActionResult(ok=True, action=action, note=f"opened {tab_id} → {url}")

            elif action == "switch_tab":
                if self._tabs is None:
                    return ActionResult(ok=False, action=action, note="TabManager not available")
                tab_id = action_dict.get("tab_id", "")
                if not tab_id:
                    # Try by index
                    idx = action_dict.get("index", 0)
                    tabs = await self._tabs.list_tabs()
                    if idx >= len(tabs):
                        return ActionResult(ok=False, action=action, note=f"tab index {idx} out of range")
                    tab_id = tabs[idx]["id"]
                await self._tabs.switch_tab(tab_id)
                return ActionResult(ok=True, action=action, note=f"switched to {tab_id}")

            elif action == "close_tab":
                if self._tabs is None:
                    return ActionResult(ok=False, action=action, note="TabManager not available")
                tab_id = action_dict.get("tab_id")
                await self._tabs.close_tab(tab_id)
                closed = tab_id or "current tab"
                return ActionResult(ok=True, action=action, note=f"closed {closed}")

            elif action == "list_tabs":
                if self._tabs is None:
                    return ActionResult(ok=False, action=action, note="TabManager not available")
                tabs = await self._tabs.list_tabs()
                return ActionResult(ok=True, action=action, note=json.dumps(tabs), extracted=json.dumps(tabs))

            # ── Terminal ──────────────────────────────────────────────────
            elif action == "done":
                summary = action_dict.get("summary", "Task completed")
                return ActionResult(ok=True, action=action, note=f"done: {summary}")

            elif action == "fail":
                reason = action_dict.get("reason", "Task failed")
                return ActionResult(ok=True, action=action, note=f"fail: {reason}")

            else:
                return ActionResult(ok=False, action=action, note=f"unknown action: {action}")

        except Exception as exc:
            return ActionResult(ok=False, action=action, note=str(exc))
