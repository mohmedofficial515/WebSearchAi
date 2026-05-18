"""End-to-end agent: plan → loop(perceive → decide → act) → verify."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import settings
from ..llm.providers import get_provider
from ..utils.event_bus import Event, bus
from ..utils.logger import log
from .browser import BrowserSession
from .executor import Executor
from .perception import Perception
from .planner import Plan, Planner
from .search_agent import SearchAgent
from .tab_manager import TabManager
from .verifier import Verifier


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
    except Exception:
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


class Agent:
    def __init__(
        self,
        *,
        headless: bool | None = None,
        use_vision: bool = True,
        user_data_dir: Path | None = None,
    ) -> None:
        self.llm = get_provider(settings)
        self.use_vision = use_vision
        self.session = BrowserSession(
            headless=settings.browser_headless if headless is None else headless,
            user_data_dir=user_data_dir,
        )
        self.perception = Perception(self.session)
        self.tab_manager: TabManager | None = None
        self.executor = Executor(self.session)
        self.planner = Planner(self.llm)
        self.verifier = Verifier(self.llm)
        # Search-first orchestrator. Pure-LLM + search-API, no browser.
        # The browser visit step is still driven from this Agent class.
        self.search_agent = SearchAgent(self.llm)

    async def __aenter__(self) -> "Agent":
        await self.session.start()
        self.tab_manager = TabManager(self.session)
        self.executor = Executor(self.session, tab_manager=self.tab_manager)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.session.stop()
        await self.llm.close()

    async def run(self, goal: str, *, task_id: str | None = None, tab_id: str | None = None) -> TaskResult:
        task_id = task_id or uuid.uuid4().hex[:10]
        artifacts = settings.output_path / "sessions" / task_id
        artifacts.mkdir(parents=True, exist_ok=True)

        await self._emit(task_id, "task_start", {"goal": goal}, tab_id=tab_id)

        memory_context = await self._get_memory_context(goal)
        # Stash on self so _decide_with_retry can forward it to the
        # decider (the decider previously saw only `goal`, which is why
        # an Arabic 'ديل' query could drift to dell.com despite the
        # planner producing a perfect subtask list).
        self._memory_context = memory_context
        plan = await self.planner.plan(goal, context=memory_context)
        await self._emit(task_id, "plan", plan.to_dict(), tab_id=tab_id)
        log.info(f"📋 Plan ready: {len(plan.subtasks)} subtasks")

        # ── Search-first agentic branch ──────────────────────────────────
        # When the user gave us KEYWORDS (no literal URL) and research
        # mode is on, we run an explicit search → rank → critique →
        # visit → judge → synthesize pipeline instead of the legacy
        # decide-loop. The legacy loop is still used for URL-bound
        # goals (clone/explore/etc.) and as a fallback if research
        # collects no useful sources at all.
        if (
            settings.research_enabled
            and not _goal_has_literal_url(goal)
            and not plan.starting_url
        ):
            try:
                research_result = await self._run_research_flow(
                    goal=goal,
                    plan=plan,
                    task_id=task_id,
                    tab_id=tab_id,
                    artifacts=artifacts,
                )
                if research_result is not None:
                    return research_result
                # research returned None → fall through to legacy loop
                # (no candidates found at all, even after re-search).
                log.warning("Research flow produced no candidates — falling back to decide loop.")
            except Exception as exc:  # noqa: BLE001
                log.warning(f"Research flow crashed ({type(exc).__name__}: {exc!s:.200}). Falling back to decide loop.")
                await self._emit(task_id, "research_error",
                                 {"error": f"{type(exc).__name__}: {exc!s:.200}"}, tab_id=tab_id)

        history: list[dict] = []
        extractions: list[str] = []
        final_summary = ""
        success_from_agent = False
        _consecutive_failures = 0
        # Loop guard: count action signatures (action_type + key field).
        # If the agent runs the SAME conceptual action 3+ times we either
        # inject an anti-loop hint or abort. Catches the failure mode
        # where the LLM keeps refining a search query that already
        # returned everything it could.
        _sig_counts: dict[str, int] = {}
        # URLs the network couldn't reach. Subsequent goto's to the same
        # host are short-circuited so the LLM can't burn 5 retries on a
        # geo-blocked or DNS-failed site.
        _dead_urls: set[str] = set()
        _loop_hint: str | None = None

        # Initial navigation, if the planner suggested one. We try it
        # but DO NOT crash the task if it fails — many planner-emitted
        # URLs are LLM guesses (e.g. "deal.sa" when the real domain is
        # "dealapp.sa"). On failure we just mark the host dead and let
        # the decide loop search_web instead.
        if plan.starting_url:
            try:
                await self.session.goto(plan.starting_url)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                log.warning(f"⚠️ Initial goto failed: {plan.starting_url} → {err[:120]}")
                if _is_network_error(err):
                    host = _host_of(plan.starting_url)
                    if host:
                        _dead_urls.add(host)
                # Seed the history with the failure so the decider sees
                # what went wrong and pivots to search_web on its first turn.
                history.append({
                    "step": 0,
                    "action": {"action": "goto", "url": plan.starting_url},
                    "ok": False,
                    "note": f"Initial navigation failed: {err[:200]}",
                })
                _loop_hint = (
                    f"The planner's guessed starting URL {plan.starting_url} "
                    f"is unreachable ({err[:80]}). Do NOT retry that URL. "
                    "Start with search_web in the goal's language to find "
                    "the correct site, then goto a result from the list."
                )

        for step in range(1, settings.max_steps_per_task + 1):
            snap = await self.perception.snapshot(include_screenshot=self.use_vision)
            shot_path = artifacts / f"step_{step:03d}.png"
            if snap.screenshot_bytes:
                shot_path.write_bytes(snap.screenshot_bytes)

            await self._emit(
                task_id,
                "perception",
                {
                    "step": step,
                    "url": snap.url,
                    "title": snap.title,
                    "n_elements": len(snap.elements),
                    "screenshot": shot_path.name,
                },
                tab_id=tab_id,
            )

            decision = await self._decide_with_retry(
                plan, history, snap, extra_hint=_loop_hint
            )
            _loop_hint = None  # hint is single-shot
            await self._emit(task_id, "decision", {"step": step, "action": decision}, tab_id=tab_id)

            # ── Pre-execution guards ────────────────────────────────────
            sig = _signature(decision)
            _sig_counts[sig] = _sig_counts.get(sig, 0) + 1

            blocked_note: str | None = None

            # Don't let the LLM retry an URL the network already rejected.
            if decision.get("action") == "goto":
                url = (decision.get("url") or "").strip()
                host = _host_of(url)
                if host and host in _dead_urls:
                    blocked_note = (
                        f"BLOCKED: {host} previously timed out / refused connection "
                        "from this network. Skipping retry."
                    )
                    log.warning(f"⚠️ {blocked_note}")

            # Repeated identical signatures → force a change of approach.
            # Press has a lower threshold (2) because pressing the same key
            # twice when nothing changed is already a clear loop signal —
            # the 40x Escape spam on overlay-blocked pages was the canary.
            elif decision.get("action") in {
                "search_web", "click", "type", "scroll", "press", "dismiss_overlay"
            } and _sig_counts[sig] >= (2 if decision.get("action") == "press" else 3):
                blocked_note = (
                    f"BLOCKED: same action signature ({sig!r}) repeated "
                    f"{_sig_counts[sig]}x — forcing strategy change."
                )
                if decision.get("action") == "press":
                    _loop_hint = (
                        f"You pressed the same key ({decision.get('key')}) "
                        "twice and nothing changed. STOP pressing it. If an "
                        "overlay is on screen, emit "
                        '{"action":"dismiss_overlay"} or click an explicit '
                        "close-button candidate listed in the snapshot. "
                        "Otherwise pick a different action entirely."
                    )
                elif decision.get("action") == "dismiss_overlay":
                    _loop_hint = (
                        "dismiss_overlay has failed multiple times. The "
                        "overlay is not handled by common selectors. Try "
                        "clicking a specific close-button candidate by "
                        "index, reload the page with goto, or emit fail "
                        "with reason 'undismissable overlay'."
                    )
                else:
                    _loop_hint = (
                        "You have repeated the SAME action 3+ times with no "
                        "new result. STOP refining the same query/click. "
                        "Either pick a fundamentally different approach "
                        "(different URL from your search results, different "
                        "query angle, different language) OR emit fail with "
                        "a clear reason."
                    )

            if blocked_note is not None:
                history.append({
                    "step": step,
                    "action": decision,
                    "ok": False,
                    "note": blocked_note,
                })
                await self._emit(task_id, "action_result",
                                 {"step": step, "ok": False, "note": blocked_note},
                                 tab_id=tab_id)
                _consecutive_failures += 1
                if _consecutive_failures >= 4:
                    final_summary = f"Aborted: {blocked_note}"
                    break
                continue

            # ── Execute ─────────────────────────────────────────────────
            result = await self.executor.run(decision)
            history.append(
                {
                    "step": step,
                    "action": decision,
                    "ok": result.ok,
                    "note": result.note,
                }
            )
            await self._emit(
                task_id,
                "action_result",
                {"step": step, "ok": result.ok, "note": result.note},
                tab_id=tab_id,
            )

            if result.extracted:
                extractions.append(result.extracted)

            # ── Post-execution: detect dead URLs from error messages ────
            if (
                not result.ok
                and decision.get("action") == "goto"
                and _is_network_error(result.note)
            ):
                url = (decision.get("url") or "").strip()
                host = _host_of(url)
                if host:
                    _dead_urls.add(host)
                    log.warning(f"🚫 Marked {host} as unreachable")
                    _loop_hint = (
                        f"The host {host} is unreachable from this network "
                        f"({result.note[:80]}). Do NOT retry that domain. "
                        "Pick a different result from your earlier search_web "
                        "results, or emit fail."
                    )

            if not result.ok:
                _consecutive_failures += 1
                if _consecutive_failures >= 4:
                    log.warning(f"⚠️ Stuck: {_consecutive_failures} consecutive failures — aborting")
                    final_summary = f"Stuck after {_consecutive_failures} repeated failures: {result.note}"
                    break
            else:
                _consecutive_failures = 0

            if decision.get("action") == "done":
                final_summary = decision.get("summary", "")
                success_from_agent = True
                break
            if decision.get("action") == "fail":
                final_summary = decision.get("reason", "agent gave up")
                break

        final_snap = await self.perception.snapshot(include_screenshot=False)
        verdict = await self.verifier.verify(
            goal=goal,
            success_criteria=plan.success_criteria,
            final_summary=final_summary or "(agent did not declare done)",
            final_snapshot_text=final_snap.render_for_llm(60),
            extractions=extractions,
        )
        await self._emit(task_id, "verdict", verdict, tab_id=tab_id)

        if bool(verdict.get("success")) and success_from_agent and plan.starting_url:
            await self._save_memory(plan, history, extractions)

        # Archive every successful task so future identical/similar
        # requests can be served from cache without firing up the browser.
        if bool(verdict.get("success")) and success_from_agent:
            await self._archive_task(
                task_id=task_id,
                goal=goal,
                plan=plan,
                history=history,
                extractions=extractions,
                final_summary=final_summary,
                verdict=verdict,
            )

        result = TaskResult(
            task_id=task_id,
            goal=goal,
            success=bool(verdict.get("success")) and success_from_agent,
            confidence=float(verdict.get("confidence") or 0.0),
            reason=str(verdict.get("reason") or ""),
            summary=final_summary,
            steps=history,
            plan=plan.to_dict(),
            extractions=extractions,
            artifacts_dir=str(artifacts),
        )
        (artifacts / "result.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await self._emit(task_id, "task_end", result.to_dict(), tab_id=tab_id)
        return result

    async def run_parallel(
        self,
        goals: list[str],
        *,
        task_id: str | None = None,
    ) -> list[TaskResult]:
        """Run multiple goals concurrently — each in its own Agent/browser instance.

        All agents emit to the same task_id but with distinct tab_id values
        (tab_0, tab_1, …) so WebSocket consumers can distinguish streams.
        """
        task_id = task_id or uuid.uuid4().hex[:10]

        async def _run_one(goal: str, tab_index: int) -> TaskResult:
            tab_id = f"tab_{tab_index}"
            async with Agent(
                headless=self.session.headless,
                use_vision=self.use_vision,
            ) as agent:
                return await agent.run(goal, task_id=task_id, tab_id=tab_id)

        await self._emit(
            task_id,
            "parallel_start",
            {"goals": goals, "count": len(goals)},
        )

        raw = await asyncio.gather(
            *[_run_one(g, i) for i, g in enumerate(goals)],
            return_exceptions=True,
        )

        results: list[TaskResult] = []
        for i, r in enumerate(raw):
            if isinstance(r, TaskResult):
                results.append(r)
            else:
                results.append(
                    TaskResult(
                        task_id=task_id,
                        goal=goals[i],
                        success=False,
                        confidence=0.0,
                        reason=str(r),
                        summary="",
                    )
                )

        await self._emit(
            task_id,
            "parallel_end",
            {
                "count": len(results),
                "succeeded": sum(1 for r in results if r.success),
            },
        )
        return results

    async def _run_research_flow(
        self,
        *,
        goal: str,
        plan: Plan,
        task_id: str,
        tab_id: str | None,
        artifacts: Path,
    ) -> TaskResult | None:
        """The agentic research pipeline.

        Steps:
          1. SearchAgent.research(goal) → ranked visit queue.
          2. FOR each candidate in queue:
                 goto → extract page text → ContentCritic verdict.
                 IF score >= threshold → add to useful_sources.
                 IF len(useful_sources) >= min_useful → break early.
          3. IF useful_sources < min and re_search rounds remain:
                 ask Critic for new queries → re-research with negative
                 feedback (avoid already-seen hosts/queries) → repeat.
          4. Synthesizer.synthesize(useful_sources) → cited answer.
          5. Verifier confirms goal achievement.
          6. Archive on success.

        Returns None ONLY when no candidates were ever found (zero
        results from every backend across every re-search) — caller
        falls back to the legacy decide-loop in that case.
        """
        # Bind the event emitter so SearchAgent can stream progress.
        async def _on_event(type_: str, data: dict) -> None:
            await self._emit(task_id, type_, data, tab_id=tab_id)

        all_queries: list[str] = []
        all_visited: list[str] = []  # URLs we tried to goto
        dead_hosts: set[str] = set()
        useful_sources: list[dict[str, Any]] = []
        extractions: list[str] = []  # raw page text (for archive + verifier)
        all_candidates_seen: list[dict] = []
        visit_log: list[dict[str, Any]] = []  # history-shaped records for TaskResult.steps
        why_not_parts: list[str] = []
        step_idx = 0

        min_useful = max(1, settings.research_min_useful_sources)
        threshold = float(settings.research_relevance_threshold)
        max_re_search = max(0, settings.research_max_re_search)

        avoid_queries: set[str] = set()

        for round_idx in range(max_re_search + 1):
            await self._emit(task_id, "research_round",
                             {"round": round_idx + 1, "useful_so_far": len(useful_sources)},
                             tab_id=tab_id)

            plan_research = await self.search_agent.research(
                goal=goal,
                avoid_hosts=dead_hosts,
                avoid_queries=avoid_queries,
                on_event=_on_event,
            )
            all_queries.extend(q for q in plan_research.queries if q not in all_queries)
            avoid_queries.update(plan_research.queries)
            all_candidates_seen.extend(c.to_dict() for c in plan_research.candidates)

            if not plan_research.visit_queue:
                why_not_parts.append(f"Round {round_idx + 1}: zero candidates from {len(plan_research.queries)} queries.")
                # If absolutely nothing came back AND we haven't visited
                # anything yet, signal to caller we can't proceed.
                if round_idx == 0 and not all_visited:
                    if max_re_search == 0:
                        return None
                    # else fall through to re-search decision below
                # try the re-search step
            else:
                # ── Visit + judge loop ──────────────────────────────
                for candidate in plan_research.visit_queue:
                    if len(useful_sources) >= min_useful:
                        break
                    step_idx += 1
                    url = candidate.url
                    host = candidate.host or _host_of(url)
                    if host and host in dead_hosts:
                        continue
                    if url in all_visited:
                        continue
                    all_visited.append(url)

                    await self._emit(task_id, "candidate_selected", {
                        "step": step_idx,
                        "url": url,
                        "title": candidate.title,
                        "final_score": candidate.final_score,
                        "reason": candidate.llm_reason,
                    }, tab_id=tab_id)

                    # ── 5a. visit ─────────────────────────────────
                    goto_ok = True
                    goto_note = ""
                    try:
                        await self.session.goto(url)
                    except Exception as exc:  # noqa: BLE001
                        goto_ok = False
                        goto_note = str(exc)[:240]
                        if _is_network_error(goto_note) and host:
                            dead_hosts.add(host)
                        why_not_parts.append(f"goto {url!r}: {goto_note[:120]}")

                    if not goto_ok:
                        visit_log.append({
                            "step": step_idx,
                            "action": {"action": "goto", "url": url},
                            "ok": False,
                            "note": goto_note,
                        })
                        await self._emit(task_id, "action_result",
                                         {"step": step_idx, "ok": False, "note": goto_note},
                                         tab_id=tab_id)
                        continue

                    visit_log.append({
                        "step": step_idx,
                        "action": {"action": "goto", "url": url},
                        "ok": True,
                        "note": f"navigated to {url}",
                    })

                    # ── 5b. screenshot + extract ────────────────────
                    try:
                        snap = await self.perception.snapshot(include_screenshot=self.use_vision)
                        if snap.screenshot_bytes:
                            (artifacts / f"step_{step_idx:03d}.png").write_bytes(snap.screenshot_bytes)
                        await self._emit(task_id, "perception", {
                            "step": step_idx,
                            "url": snap.url,
                            "title": snap.title,
                            "n_elements": len(snap.elements),
                        }, tab_id=tab_id)
                    except Exception as exc:  # noqa: BLE001
                        log.debug(f"perception failed on {url}: {exc}")

                    extract_chars = int(getattr(settings, "research_extract_chars", 14000))
                    try:
                        raw = await self.session.eval_js("document.body.innerText")
                        page_text = str(raw or "")[:extract_chars]
                    except Exception as exc:  # noqa: BLE001
                        page_text = ""
                        why_not_parts.append(f"extract {url!r}: {exc!s:.120}")

                    if page_text:
                        extractions.append(page_text[: max(4000, extract_chars // 2)])

                    # ── 5c. content critic ──────────────────────────
                    step_idx += 1
                    verdict = await self.search_agent.judge_content(goal, url, page_text)
                    await self._emit(task_id, "content_critiqued", {
                        "step": step_idx,
                        "url": url,
                        "score": verdict.score,
                        "verdict": verdict.verdict,
                        "useful_facts": verdict.useful_facts,
                    }, tab_id=tab_id)
                    visit_log.append({
                        "step": step_idx,
                        "action": {"action": "judge_content", "url": url},
                        "ok": True,
                        "note": f"score={verdict.score:.2f} — {verdict.verdict}",
                    })

                    if verdict.score >= threshold and verdict.useful_facts:
                        useful_sources.append({
                            "url": url,
                            "title": candidate.title,
                            "verdict": verdict.verdict,
                            "useful_facts": verdict.useful_facts,
                            "score": verdict.score,
                        })
                    else:
                        why_not_parts.append(
                            f"{url}: score={verdict.score:.2f} — {verdict.verdict or 'low relevance'}"
                        )

            # Enough? bail before doing another search round.
            if len(useful_sources) >= min_useful:
                break

            # Last round — no more re-searches available.
            if round_idx >= max_re_search:
                break

            # ── Re-search decision ──────────────────────────────────
            decision = await self.search_agent.decide_re_search(
                goal=goal,
                queries_tried=all_queries,
                urls_visited=all_visited,
                useful_facts=[f for s in useful_sources for f in s.get("useful_facts", [])],
                why_not="\n".join(why_not_parts[-12:]),
            )
            await self._emit(task_id, "re_search_decision", decision.to_dict(), tab_id=tab_id)
            if not decision.should_re_search or not decision.new_queries:
                break
            # Seed the next round: critic-proposed queries get priority,
            # already-tried queries are blocked via `avoid_queries`.
            avoid_queries.update(all_queries)
            # The next research() call will run its own query generator;
            # we splice the critic's new queries in by temporarily
            # monkey-injecting them via avoid_queries (negative) and a
            # one-shot override on the orchestrator's generator. The
            # simplest robust path: pre-seed `avoid_queries` so the
            # generator must produce different angles, and pass the
            # critic's queries by appending them to the goal hint.
            goal_hint = goal + " | retry-angles: " + " ; ".join(decision.new_queries[:3])
            goal = goal_hint  # next round uses the broader hint

        # ── Synthesize ────────────────────────────────────────────────
        synth = await self.search_agent.synthesize(goal, useful_sources)
        await self._emit(task_id, "synthesis_done", synth.to_dict(), tab_id=tab_id)

        final_summary = synth.answer or "(no answer)"

        # ── Verify (reuses existing Verifier for consistency) ─────────
        verdict = await self.verifier.verify(
            goal=goal,
            success_criteria=plan.success_criteria,
            final_summary=final_summary,
            final_snapshot_text="(research mode — see synthesis citations)",
            extractions=extractions,
        )
        # Blend verifier verdict with synthesizer self-critique. A
        # research run only counts as success if BOTH agree and we
        # actually collected useful_sources.
        agent_success = bool(useful_sources) and synth.addresses_goal
        success = bool(verdict.get("success")) and agent_success
        confidence = max(
            float(verdict.get("confidence") or 0.0),
            float(synth.confidence or 0.0),
        ) if success else min(
            float(verdict.get("confidence") or 0.0),
            float(synth.confidence or 0.0),
        )
        await self._emit(task_id, "verdict", verdict, tab_id=tab_id)

        if success:
            await self._archive_task(
                task_id=task_id,
                goal=goal,
                plan=plan,
                history=visit_log,
                extractions=extractions,
                final_summary=final_summary,
                verdict={**verdict, "confidence": confidence},
            )

        result = TaskResult(
            task_id=task_id,
            goal=goal,
            success=success,
            confidence=confidence,
            reason=str(verdict.get("reason") or "") or synth.feedback,
            summary=final_summary,
            steps=visit_log,
            plan={
                **plan.to_dict(),
                "research": {
                    "queries": all_queries,
                    "candidates_seen": all_candidates_seen[:20],
                    "useful_sources": useful_sources,
                    "synthesis": synth.to_dict(),
                },
            },
            extractions=extractions,
            artifacts_dir=str(artifacts),
        )
        (artifacts / "result.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Render the Arabic Markdown report alongside the raw JSON so
        # both the CLI and the web UI can show something readable
        # instead of a JSON blob. Failure here must NOT mask success.
        try:
            from ..reports import write_arabic_report
            report_path = write_arabic_report(result.to_dict(), artifacts)
            await self._emit(task_id, "report_ready",
                             {"path": str(report_path), "format": "markdown"},
                             tab_id=tab_id)
        except Exception as exc:  # noqa: BLE001
            log.debug(f"Markdown report write skipped: {exc}")

        await self._emit(task_id, "task_end", result.to_dict(), tab_id=tab_id)
        return result

    async def _decide_with_retry(
        self,
        plan: Plan,
        history: list[dict],
        snap,
        *,
        extra_hint: str | None = None,
    ) -> dict[str, Any]:
        # When the agent loop detects repetition or a dead URL it passes
        # an inline hint here. We prepend it to the snapshot text so it
        # rides into the very next LLM decision call — single-shot.
        snap_text = snap.render_for_llm()
        if extra_hint:
            snap_text = f"⚠️  AGENT HINT: {extra_hint}\n\n" + snap_text
        for attempt in range(settings.max_retries_per_step):
            try:
                decision = await self.planner.decide(
                    goal=plan.goal,
                    history=history,
                    snapshot_text=snap_text,
                    screenshot_bytes=snap.screenshot_bytes if self.use_vision else None,
                    use_vision=self.use_vision and attempt == 0,
                    subtasks=plan.subtasks,
                    context=getattr(self, "_memory_context", None),
                )
                if isinstance(decision, dict) and decision.get("action"):
                    return decision
            except Exception as e:  # noqa: BLE001
                log.warning(f"decide failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2)
        return {"action": "fail", "reason": "Planner could not produce a valid action"}

    async def _get_memory_context(self, goal: str) -> str | None:
        """Build a planner-context hint from prior successful runs.

        Two sources are consulted, and any that fire are concatenated:
          (1) Site-flow memory — a previously successful flow on a
              domain mentioned literally in the goal.
          (2) Task archive — a paraphrase of this goal we've already
              answered. Used at a *lower* threshold than the auto-cache
              short-circuit, because here we're not replacing the run,
              we're just disambiguating it. e.g. user types "تطبيق ديل"
              today; a week ago they ran "تطبيق ديل العقاري" — we surface
              "ديل ⇒ dealapp.sa real estate" so the LLM doesn't drift
              to dell.com.
        """
        parts: list[str] = []

        # (1) site-flow memory (existing behaviour) ---------------------
        try:
            import re
            from urllib.parse import urlparse
            from ..memory import get_memory

            m = re.search(r"https?://[^\s]+", goal)
            if m:
                domain_url = f"https://{urlparse(m.group(0)).netloc}"
                if urlparse(domain_url).netloc:
                    mem = await get_memory()
                    cached = await mem.recall_flow(domain_url, "browse")
                    if cached:
                        parts.append(
                            f"Previously successful flow for "
                            f"{urlparse(domain_url).netloc} "
                            f"({cached.get('success_count', 1)} run(s)):\n"
                            + json.dumps(cached["flow_data"], ensure_ascii=False)
                        )
        except Exception as exc:
            log.debug(f"Memory context (site-flow) skipped: {exc}")

        # (2) archive paraphrase hint ----------------------------------
        # Skipped when research_fresh_runs is on — the user explicitly
        # asked never to bias new runs on cached answers. Site-flow
        # memory (above) still applies because that's login plumbing,
        # not goal-answer reuse.
        if getattr(settings, "research_fresh_runs", True):
            return "\n\n".join(parts) if parts else None
        try:
            from ..archive import get_archive
            arc = await get_archive()
            # Threshold here is below the auto-cache threshold but
            # above noise. 0.35–0.85 means "you've answered something
            # related — use it to ground the new run."
            hit = await arc.find_similar(goal, threshold=0.35)
            if hit and hit.score < 0.85:  # 0.85+ is handled by /api/run cache
                rec = hit.record
                # Pull a short snippet of the prior summary to anchor
                # the model. Hard-cap to keep the planner prompt tight.
                summary = rec.summary
                if isinstance(summary, dict):
                    summary = json.dumps(summary, ensure_ascii=False)[:300]
                summary = str(summary or "")[:300]
                starting_url = rec.starting_url or ""
                terms = ", ".join(hit.matched_terms[:6]) or "(none)"
                parts.append(
                    "PRIOR-RUN HINT (use to disambiguate, do NOT copy "
                    "the answer — the user may want fresh info):\n"
                    f"  past goal: {rec.goal!r}\n"
                    f"  similarity: {hit.score:.2f} (shared terms: {terms})\n"
                    f"  past answer was about: {summary}\n"
                    + (f"  past starting URL that worked: {starting_url}\n"
                       if starting_url else "")
                    + "If the current goal is asking about the SAME entity "
                    "(same app/site/topic), trust the past starting URL "
                    "instead of guessing a new one."
                )
        except Exception as exc:
            log.debug(f"Memory context (archive) skipped: {exc}")

        return "\n\n".join(parts) if parts else None

    async def _archive_task(
        self,
        *,
        task_id: str,
        goal: str,
        plan: Plan,
        history: list[dict],
        extractions: list[str],
        final_summary: str,
        verdict: dict,
    ) -> None:
        """Persist a successful task to the durable archive so a future
        identical/similar request can short-circuit to the cached answer."""
        try:
            from ..archive import get_archive

            archive = await get_archive()
            result_payload = {
                "task_id": task_id,
                "goal": goal,
                "success": True,
                "confidence": float(verdict.get("confidence") or 0.0),
                "summary": final_summary,
                "reason": str(verdict.get("reason") or ""),
                "plan": plan.to_dict(),
                "steps": history,
                "extractions": extractions,
            }
            await archive.save(task_id, goal, result_payload)
            log.info(f"📚 Archived task {task_id}: {goal[:60]!r}")
        except Exception as exc:  # noqa: BLE001
            log.debug(f"Archive save skipped: {exc}")

    async def _save_memory(
        self, plan: Plan, history: list[dict], extractions: list[str]
    ) -> None:
        try:
            from ..memory import get_memory

            mem = await get_memory()
            await mem.touch_site(plan.starting_url)  # type: ignore[arg-type]
            flow = {
                "subtasks": plan.subtasks,
                "step_count": len(history),
                "extractions": extractions[:3],
            }
            await mem.remember_flow(plan.starting_url, "browse", flow)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            log.debug(f"Memory save skipped: {exc}")

    async def _emit(self, task_id: str, type_: str, data: dict, tab_id: str | None = None) -> None:
        await bus.publish(Event(task_id=task_id, type=type_, data=data, tab_id=tab_id))
