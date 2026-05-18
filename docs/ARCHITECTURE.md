# 🏗️ Architecture

> How WebSearchAi is put together: components, data flow, and the contracts between them.

---

## 🎯 Design goals

1. **One agent loop, many skills** — every high-level skill (`signup`, `login`, `explore`, `clone`) is a thin wrapper around the same Plan→Perceive→Decide→Act→Verify loop.
2. **Stateless core, stateful periphery** — `core/` is pure logic; state (memory, profiles, artifacts) lives in `outputs/` and (later) `src/memory/`.
3. **LLM-frugal** — vision only when text fails; cache aggressively; one decision per step.
4. **Event-streamed** — every meaningful moment is a typed `Event` on the bus, consumed by WebSocket and disk simultaneously.
5. **Fail loud, fail typed** — a captcha, rate-limit, or selector miss returns a `fail` action with structured `reason`, never a swallowed exception.

---

## 🔭 System view

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Surface                            │
│   ┌──────────┐    ┌──────────┐    ┌──────────────┐              │
│   │  Web UI  │    │   CLI    │    │  REST + WS   │              │
│   └────┬─────┘    └────┬─────┘    └──────┬───────┘              │
│        │               │                  │                     │
└────────┼───────────────┼──────────────────┼─────────────────────┘
         │               │                  │
         └───────────────┴──────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────┐
        │          FastAPI app             │
        │   src/api/main.py + tasks.py     │
        │  ┌────────────────────────────┐  │
        │  │     TaskManager            │  │
        │  │   (asyncio background)     │  │
        │  └────────────────────────────┘  │
        └────────────────┬─────────────────┘
                         │ dispatches
                         ▼
        ┌──────────────────────────────────────┐
        │           Skill layer                │
        │   signup · login · explore · clone   │
        │              + run                   │
        └────────────────┬─────────────────────┘
                         │ uses
                         ▼
        ┌──────────────────────────────────────┐
        │            Agent loop                │
        │                                      │
        │   Planner ──► Perception ──► Decider │
        │      ▲                          │    │
        │      │                          ▼    │
        │   Verifier ◄─────── Executor ◄──┘    │
        │                                      │
        └────┬──────────────────────┬──────────┘
             │                      │
             ▼                      ▼
   ┌──────────────────┐    ┌──────────────────┐
   │   MistralClient  │    │  BrowserSession  │
   │  text + vision   │    │   Playwright     │
   │   + retries      │    │   + stealth      │
   └──────────────────┘    └──────────────────┘

             ▲                      ▲
             │                      │
   ┌─────────┴──────────────────────┴───────────┐
   │             EventBus (async pub/sub)       │
   │                                            │
   │   plan · perception · decision · result    │
   │   · verdict · task_end                     │
   └────────────────────────────────────────────┘
                          │
                          ▼
   ┌────────────────────────────────────────────┐
   │   outputs/  — sessions, reports, logs      │
   │   (later: memory.db, profiles, baselines)  │
   └────────────────────────────────────────────┘
```

---

## 🧩 Component contracts

### `BrowserSession` (`src/core/browser.py`)

The only thing in the system that talks to Playwright.

**Contract:**
- One instance == one Chromium context + one page (multi-tab is Phase 3)
- All high-level actions humanize by default (`humanize=True`)
- Always honors `enable_stealth` and `Sec-Ch-Ua` overrides
- Methods: `goto`, `click`, `type`, `press`, `scroll`, `wait_for`, `screenshot`, `url`, `title`, `html`, `eval_js`

**Why this matters:** every other component receives a `BrowserSession` and never instantiates Playwright directly. This lets us swap engines (e.g., to remote Browserbase) in one place.

---

### `Perception` (`src/core/perception.py`)

Turns the current page into something the LLM can reason about.

**Output:** `Snapshot` with:
- `url`, `title`
- `elements: list[Element]` — every visible interactive element gets a stable integer index and a CSS selector via injected `data-wsai-idx` attribute
- `screenshot_bytes` — only if `include_screenshot=True`
- `render_for_llm(max_elements=80)` — compact text rendering for the prompt

**Why integer indexes:** the LLM never sees raw CSS selectors. It says `click index 12` and the executor maps that to `[data-wsai-idx="12"]`. This is robust to LLM hallucination — it can only reference elements that actually exist.

---

### `Planner` (`src/core/planner.py`)

Two LLM personas behind one class:

| Method | Prompt | Output |
|---|---|---|
| `plan(goal)` | `SYSTEM_PLANNER` — strategic | `Plan(goal, subtasks, success_criteria, starting_url)` |
| `decide(goal, history, snapshot, screenshot?)` | `SYSTEM_DECIDER` — tactical | `dict` with one action |

**Why split:** the planner runs once per task; the decider runs once per step. The decider needs to be fast and JSON-strict.

---

### `Executor` (`src/core/executor.py`)

Translates decided JSON actions into `BrowserSession` calls.

**Action grammar:** see `docs/API.md#action-schema`.

**Failure semantics:** every executor method returns `ActionResult(ok: bool, action, note, extracted?)`. The `ok=False` path never raises — it goes into history so the LLM can try a different approach.

**Critical invariant:** `note` must contain real evidence of what happened (e.g., for `extract`: the first 300 chars of extracted text). Otherwise the LLM hallucinates that extraction was empty and retries.

---

### `Verifier` (`src/core/verifier.py`)

Asks one LLM call: "given goal, criteria, summary, extractions, snapshot — did we succeed?"

**Rules baked into the prompt:**
1. **Extractions are primary evidence.** A raw-JSON page (httpbin) has zero interactive elements; that's not failure.
2. Success criteria are guidelines, not hard gates — the verifier judges semantically.
3. Returns `{success: bool, confidence: 0-1, reason: str, missing: [...]}`.

---

### `Agent` (`src/core/agent.py`)

The orchestrator. Lifecycle:

```python
async with Agent() as agent:
    result = await agent.run(goal)
```

**Step loop (max `MAX_STEPS_PER_TASK`):**
1. Perceive → screenshot saved to `outputs/sessions/<task_id>/step_NNN.png`
2. Decide → with vision on attempt 0, text fallback for retries
3. Execute → result appended to history
4. If action is `done` / `fail` → break

**Retry behavior:** `_decide_with_retry` tries up to `MAX_RETRIES_PER_STEP` times. If all fail, emits `{action: "fail", reason: "Planner could not produce a valid action"}`.

---

### `EventBus` (`src/utils/event_bus.py`)

In-memory async pub/sub.

**Event types:**
- `task_start` — `{goal}`
- `plan` — full plan dict
- `perception` — `{step, url, title, n_elements, screenshot}`
- `decision` — `{step, action}`
- `action_result` — `{step, ok, note}`
- `verdict` — verifier output
- `task_end` — full `TaskResult`

**Subscribers:**
- WebSocket connections (`/ws/{task_id}`)
- (Later, Phase 10) OpenTelemetry exporter
- (Later, Phase 2) Memory writer

---

### `TaskManager` (`src/api/tasks.py`)

Asyncio background task queue.

**States:** `queued` → `running` → `succeeded` | `failed` | `cancelled`

**Why in-memory now:** the MVP runs single-process. Phase 6 swaps this for Redis-backed `arq` or `dramatiq`.

---

## 🌊 Data flow: a single `run` task

```
User                    API                   Skill              Agent loop
 │                       │                      │                    │
 ├─POST /api/run────────▶│                      │                    │
 │                       ├─tasks.submit("run")─▶│                    │
 │◀──{task_id, queued}───┤                      │                    │
 │                       │                      ├─agent.run(goal)───▶│
 │                       │                      │                    ├─planner.plan
 │                       │                      │                    ├─session.start
 │                       │                      │                    ├─session.goto(starting_url)
 │                       │                      │                    │
 │  WS /ws/{task_id}     │                      │                    │ ┌───────────┐
 ├──────────────────────▶│                      │                    │ │ for step  │
 │                       │                      │                    │ │ in range  │
 │◀──"perception"────────┤◀── event bus ◄───────┼────────────────────┤◀│ ┌─────── │
 │◀──"decision"──────────┤                      │                    │ │ │ ...   ││
 │◀──"action_result"─────┤                      │                    │ │ └────────│
 │                       │                      │                    │ └───────────┘
 │                       │                      │                    ├─verifier.verify
 │◀──"verdict"───────────┤                      │                    │
 │◀──"task_end"──────────┤◀──TaskResult─────────┤◀───────────────────┤
```

---

## 🔒 Stealth strategy

What we do to look human:

| Layer | Technique | File |
|---|---|---|
| Network | Override `Sec-Ch-Ua` headers, set `timezone_id`, real desktop UA | `core/browser.py` |
| JS | `navigator.webdriver=undefined`, fake `plugins`, fake `permissions.query` | `core/browser.py` |
| Mouse | Bezier curves with jitter, never instant teleport | `utils/human_behavior.py` |
| Keyboard | WPM-based typing with per-char delay variance | `utils/human_behavior.py` |
| Cadence | `random_delay(300–1200ms)` after every action | `utils/human_behavior.py` |
| Cookies | `launch_persistent_context` when `user_data_dir` set | `core/browser.py` |

What we deliberately don't do:
- Solve captchas (legal/ethical line)
- Rotate IPs automatically (use `HTTP_PROXY` if needed)
- Bypass 2FA

---

## 🗄️ Persistence layout

```
outputs/
├── sessions/<task_id>/
│   ├── step_001.png      ← screenshots per step
│   ├── step_002.png
│   └── result.json       ← full TaskResult
├── reports/
│   └── github.com.json   ← explore reports
├── cloned_sites/
│   └── tailwindcss.com/  ← clone outputs
├── profiles/             ← persistent browser profiles
│   └── <profile_name>/
├── memory.db             ← Phase 2: SQLite memory
└── websearchai.log       ← rolling app log
```

---

## 📦 Module dependency graph

```
api ──────► skills ──────► core/agent ──┬──► core/planner ──► llm
                                        ├──► core/perception ──► core/browser
                                        ├──► core/executor ───► core/browser
                                        └──► core/verifier ──► llm

core/* ──► utils/* (logger, event_bus, human_behavior, temp_mail)
core/* ──► config

(none of the lower layers depend on api or skills — clean unidirectional flow)
```

**Rule:** never let `utils/` or `llm/` import from `core/`, `skills/`, or `api/`.

---

## 🧪 Testing strategy

| Layer | Test type | Tooling |
|---|---|---|
| `utils/`, `llm/`, helpers | Unit tests, mocked HTTP | `pytest`, `respx` |
| `core/planner`, `core/verifier` | LLM-mocked unit tests | `pytest`, response fixtures |
| `core/executor` | Integration: real Playwright on local HTML | `pytest-playwright` |
| `skills/*` | End-to-end against `httpbin.org` | `pytest`, slow lane |
| `api/*` | TestClient + WS test | `httpx.AsyncClient`, `starlette.testclient` |

CI runs unit + fast integration on every PR; the full E2E suite runs nightly.

---

## 🔁 Extension points

When adding a new feature, prefer these locations:

| To add… | Put it in… |
|---|---|
| A new high-level capability | `src/skills/<name>.py` |
| A new browser action | `Executor.run` + `ACTION_SCHEMA_DESC` in planner |
| A new LLM provider | `src/llm/providers/<name>.py` (Phase 9) |
| A new event type | `src/utils/event_bus.py` + WS consumer |
| A new config knob | `src/config.py` + `.env.example` |
| A new API endpoint | `src/api/main.py` + Web UI tab |

---

## 🚦 Performance budgets

| Path | Budget | Why |
|---|---|---|
| Perception (DOM walk + screenshot) | < 1.5s | Otherwise step latency dominates |
| Planner.decide (one LLM call) | < 8s p95 | Mistral free tier ceiling |
| Full simple task (httpbin) | < 30s | 2 steps × ~12s |
| Explore task (medium site) | < 4 min | 10-20 steps + final report call |

If you blow a budget, the fix is almost always: cut LLM calls or batch perception, not parallelize.
