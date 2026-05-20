"""Pure helpers + result dataclass extracted from `src/core/agent.py`.

These have no dependency on the `Agent` instance (no `self`) and are
useful in isolation — search heuristics, URL utilities, and a stable
"decision signature" used by the loop-detection guard.

`TaskResult` lives here too so callers can import it without pulling
the full Agent dependency graph (Playwright, providers, perception).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://[^\s)\]<>]+", re.IGNORECASE)


def _goal_has_literal_url(goal: str) -> bool:
    """True iff the goal contains a full http(s):// URL the user typed.

    Search-first only kicks in when no URL is present — if the user
    pastes 'summarize https://example.com/x' we keep the existing
    direct-navigation flow."""
    return bool(_URL_RE.search(goal or ""))


# ── Loop-detection helpers ───────────────────────────────────────────────────

# Connection-error substrings emitted by Playwright when a host is
# unreachable. If we see one, we mark the host dead so the LLM can't
# retry it 5x. This is a defensive list — anything that looks like a
# network-layer failure counts.
_NETWORK_ERROR_PATTERNS = (
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_RESET",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_NETWORK_CHANGED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_SOCKS_CONNECTION_FAILED",
    "net::ERR_",
    "Timeout 30000ms exceeded",
)


def _is_network_error(note: str) -> bool:
    if not note:
        return False
    s = str(note)
    return any(p in s for p in _NETWORK_ERROR_PATTERNS)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except (ValueError, AttributeError):
        return ""


def _normalize_query(text: str) -> str:
    """Strip whitespace, lowercase, drop site:/quoted operators so we
    can tell when two ‘different’ search queries are functionally the
    same. Without this the LLM dodges loop-detection by tacking on
    `site:foo.com` then `site:bar.com` then `site:foo.com OR site:bar.com`."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"\bsite:\S+", "", t)
    t = re.sub(r"\boR\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[\"'`]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _signature(decision: dict) -> str:
    """Stable signature of a decision for loop detection.

    Two decisions share a signature when they're conceptually the
    same act. Tiny edits to a search query (adding `site:` filters,
    swapping `for` for `in`) MUST still collapse, otherwise the LLM
    can drift in circles forever without tripping the guard."""
    a = (decision or {}).get("action", "")
    if a == "search_web":
        return "search_web:" + _normalize_query(str(decision.get("query") or ""))
    if a == "goto":
        return "goto:" + _host_of(str(decision.get("url") or ""))
    if a == "click":
        return f"click:{decision.get('index')}"
    if a == "type":
        return f"type:{decision.get('index')}:{_normalize_query(str(decision.get('text') or ''))[:40]}"
    if a == "press":
        # Include the key so 'press Escape' x40 actually collapses to
        # the same signature and trips the anti-loop guard.
        return f"press:{(decision.get('key') or '').strip()}"
    if a == "dismiss_overlay":
        return "dismiss_overlay"
    if a in {"scroll", "wait"}:
        return f"{a}:{decision.get('direction') or decision.get('seconds') or decision.get('ms') or ''}"
    return a or "unknown"


@dataclass
class TaskResult:
    task_id: str
    goal: str
    success: bool
    confidence: float
    reason: str
    summary: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    extractions: list[str] = field(default_factory=list)
    artifacts_dir: str | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "success": self.success,
            "confidence": self.confidence,
            "reason": self.reason,
            "summary": self.summary,
            "steps": self.steps,
            "plan": self.plan,
            "extractions": self.extractions,
            "artifacts_dir": self.artifacts_dir,
        }


__all__ = [
    "TaskResult",
    "_URL_RE",
    "_NETWORK_ERROR_PATTERNS",
    "_goal_has_literal_url",
    "_is_network_error",
    "_host_of",
    "_normalize_query",
    "_signature",
]
