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
                try:
                    await self._s.click(sel)
                    return ActionResult(ok=True, action=action, note=f"clicked {sel}")
                except Exception as click_exc:
                    # Auto-recovery: timeout/intercept usually means an
                    # overlay is in the way. Try dismissing once and retry
                    # the click before bubbling the error up. Saves the
                    # agent from burning steps re-clicking a blocked target.
                    msg = str(click_exc)
                    if "Timeout" in msg or "intercept" in msg:
                        dismiss = await self._s.dismiss_overlay()
                        if dismiss.get("ok"):
                            await self._s.click(sel)
                            return ActionResult(
                                ok=True, action=action,
                                note=f"clicked {sel} (auto-dismissed overlay via {dismiss.get('via')})",
                            )
                    raise

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
                # Planner schema uses "seconds"; older callers may pass "ms".
                # Accept both so the LLM doesn't get a silent 1-second default
                # when it asks for {"seconds": 5}.
                if "seconds" in action_dict:
                    ms = int(float(action_dict.get("seconds") or 1) * 1000)
                else:
                    ms = int(action_dict.get("ms") or 1000)
                ms = max(0, min(ms, 15_000))  # hard-cap at 15s to prevent stalls
                await asyncio.sleep(ms / 1000)
                return ActionResult(ok=True, action=action, note=f"waited {ms}ms")

            elif action == "extract":
                raw = await self._s.eval_js("document.body.innerText")
                text = str(raw or "")[:4000]
                return ActionResult(ok=True, action=action, note=text, extracted=text)

            # ── Overlay dismissal (smart) ────────────────────────────────
            # Tries 20+ common selectors (close buttons, cookie banners,
            # Bootstrap data-dismiss) and falls back to Escape. Returns a
            # clear note so the LLM knows whether to retry or change tactic.
            elif action == "dismiss_overlay":
                res = await self._s.dismiss_overlay()
                ok = bool(res.get("ok"))
                via = res.get("via", "?")
                if ok:
                    note = f"overlay dismissed via {via}"
                else:
                    note = (
                        f"overlay still present after trying {via}. Next: try clicking a "
                        "specific close-button candidate from the snapshot, reload the page "
                        "with goto, or emit fail if the overlay is undismissable."
                    )
                return ActionResult(ok=ok, action=action, note=note)

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
