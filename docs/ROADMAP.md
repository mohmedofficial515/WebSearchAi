# 🗺️ WebSearchAi — Full Roadmap

> A multi-phase, multi-year plan from the current Phase 1 MVP to a production-grade autonomous browsing platform.

---

## 📊 Current state

**Phase 1 — Core Agent (✅ Shipped)**

The MVP is operational with:
- Plan → Perceive → Decide → Act → Verify loop
- Mistral (text + Pixtral vision) LLM driver
- Playwright stealth browser (Chromium, Sec-Ch-Ua override, persistent context)
- 5 skills: `run`, `signup`, `login`, `explore`, `clone`
- FastAPI + WebSocket Web UI
- CLI (Typer)
- Tested on github.com explore → 19 features extracted, full design palette, 15-step clone recipe

| Metric | Value |
|---|---|
| LOC (Python) | ~1,640 |
| LOC (Web UI) | ~440 |
| LLM calls / explore task | ~3 |
| Avg tokens / task | 3K–8K |
| Free tier capacity | ~60–150 explore tasks / month |

---

## 🎯 North-star principles

1. **Human-cadence first** — every action looks human; never burst-click or hit rate limits.
2. **LLM-cheap by default** — cache aggressively, only call vision when text fails, batch perception.
3. **Skill-pluggable** — new capabilities slot in as `src/skills/<name>.py` with no core changes.
4. **Observable** — every step emits a typed event the UI/CLI/disk can subscribe to.
5. **Failure-aware** — bot challenges, captchas, and rate-limits trigger structured `fail` actions, not silent retries.

---

## 🛣️ Roadmap (10 phases)

Each phase has: **Goal**, **Deliverables**, **Acceptance criteria**, **Effort**, **Dependencies**.

---

### Phase 2 — Long-term Memory & Skill Library
**Goal:** The agent remembers sites it has visited, learns successful flows, and reuses them.

**Deliverables:**
- `src/memory/store.py` — SQLite-backed memory (sites, flows, selectors, login profiles)
- `src/memory/recall.py` — semantic retrieval: "have I logged into stripe.com before?"
- `src/skills/library.py` — pre-baked flows: `google_search`, `youtube_search`, `linkedin_extract_profile`
- Embeddings: `mistral-embed` (free tier) for similarity search
- New CLI: `python run.py memory list` / `memory forget <site>`

**Acceptance:**
- Second login to the same site uses cached selectors → < 5 steps
- Memory survives restarts (sqlite file in `outputs/memory.db`)
- Cost: zero extra LLM calls when a cached flow matches

**Effort:** 2-3 days · **Depends on:** Phase 1

---

### Phase 3 — Multi-Tab & Parallel Orchestration
**Goal:** Run multiple browser tabs concurrently; one agent orchestrates them.

**Deliverables:**
- `src/core/tab_manager.py` — owns N pages within one context
- `Executor` actions: `open_tab`, `switch_tab`, `close_tab`
- `Planner` prompt extension: "you may operate K tabs in parallel"
- API: `POST /api/run` accepts `parallel_goals: [str]` → spawns one agent per tab
- WebSocket events carry `tab_id`

**Acceptance:**
- Compare 3 product pages in one task, ~2× faster than sequential
- No deadlocks or lost screenshots when tabs interleave

**Effort:** 3-4 days · **Depends on:** Phase 1

---

### Phase 4 — Visual Diff & Regression Testing
**Goal:** Compare expected vs actual screenshots; flag UI regressions.

**Deliverables:**
- `src/skills/visual_test.py` — captures baselines, computes pixel + perceptual diffs
- `pixelmatch-py` or `opencv` for diff
- `outputs/baselines/<site>/<page>.png` storage
- Web UI tab: "Visual Regressions" — gallery of diffs with side-by-side viewer
- New CLI: `python run.py vtest <url> --baseline / --check`

**Acceptance:**
- Baselines auto-saved on first capture
- Diff > 5% area triggers a `fail` verdict with screenshot annotation
- False positives < 5% on a 10-site test set

**Effort:** 2-3 days · **Depends on:** Phase 1

---

### Phase 5 — Full-Site Cloning (multi-page)
**Goal:** Clone a whole site, not just one page — sitemap crawl + asset rewriter + link graph.

**Deliverables:**
- `src/skills/site_clone.py` — sitemap discovery (`/sitemap.xml`, robots.txt, link-graph BFS)
- Asset rewriter: relative-path all CSS/JS/images, rewrite internal links
- AI rebuild per-page → consistent Tailwind theme across pages
- Output: `outputs/cloned_sites/<domain>/` ready to `python -m http.server`

**Acceptance:**
- Clones a 20-page docs site in < 10 min
- All internal links work when served locally
- Brand colors and typography are consistent across pages

**Effort:** 4-5 days · **Depends on:** Phase 1

---

### Phase 6 — Docker + Remote Agent Runner
**Goal:** One-command deployment; run agents on a remote server.

**Deliverables:**
- `Dockerfile` (multi-stage: builder + slim runtime with Playwright deps)
- `docker-compose.yml` — app + optional redis for queue
- `scripts/deploy.sh` — deploy to Fly.io / Railway / Hetzner
- Health check: `GET /api/health`
- Optional: Redis-backed task queue (replaces in-memory dict for HA)

**Acceptance:**
- `docker compose up` → working web UI on `http://localhost:8000`
- Image size < 1.5 GB
- Survives container restart with persisted memory.db

**Effort:** 2 days · **Depends on:** Phase 1

---

### Phase 7 — Plugin System & Custom Skills
**Goal:** Third parties write skills as drop-in plugins without touching core.

**Deliverables:**
- `src/skills/plugin_loader.py` — auto-discovers `~/.websearchai/plugins/*.py`
- Plugin contract: `class Skill(Protocol)` with `name`, `params_schema`, `run()`
- `scripts/scaffold-skill.py` — generates a skeleton from template
- Docs: `docs/SKILLS.md` walkthrough writing a new skill

**Acceptance:**
- Drop a `.py` file in plugin dir → appears in Web UI tabs & CLI commands
- Plugin can use Mistral LLM, browser, memory — all via stable interfaces

**Effort:** 2-3 days · **Depends on:** Phase 2

---

### Phase 8 — Authentication & Multi-User
**Goal:** Multiple users with isolated browser profiles, API keys, and quotas.

**Deliverables:**
- `src/api/auth.py` — JWT auth, user table in SQLite
- Per-user browser profiles in `outputs/profiles/<user_id>/`
- Per-user task quotas (configurable in `.env`: `FREE_TASKS_PER_DAY=20`)
- Web UI: login screen, user settings page, API key generation

**Acceptance:**
- Two users see only their own tasks
- API key rotation works
- Quota exhaustion returns 429 with reset-time header

**Effort:** 3-4 days · **Depends on:** Phase 6

---

### Phase 9 — LLM Provider Abstraction
**Goal:** Swap Mistral for OpenAI / Anthropic / Gemini / local Ollama with one env var.

**Deliverables:**
- `src/llm/base.py` — `LLMClient` protocol
- `src/llm/providers/{mistral,openai,anthropic,ollama}.py`
- Auto-fallback chain: try free → paid → local
- Cost tracker: `outputs/costs.jsonl` with per-call $ tracking

**Acceptance:**
- All 5 skills work on each provider without code changes
- Failover: if Mistral returns 429, retry on next provider
- Cost dashboard at `/api/costs` shows daily spend

**Effort:** 3 days · **Depends on:** Phase 1

---

### Phase 10 — Production Observability
**Goal:** Know what every agent is doing, where it spends time, why it failed.

**Deliverables:**
- OpenTelemetry traces (each step → span)
- Prometheus `/metrics` endpoint (task duration, success rate, LLM cost)
- Structured JSON logs with rotation
- Grafana dashboard JSON in `docs/grafana/`
- Sentry integration for unhandled exceptions

**Acceptance:**
- p50 / p99 task latency visible in Grafana
- Alert when success rate < 70% over 1h
- Full distributed trace from API call → LLM call → Playwright call

**Effort:** 2-3 days · **Depends on:** Phase 6

---

## 📅 Suggested timeline

| Quarter | Phases | Theme |
|---|---|---|
| Q1 2026 | ✅ Phase 1 | MVP shipped |
| Q2 2026 | Phase 2, 3 | Smarter agent — memory & parallelism |
| Q3 2026 | Phase 4, 5 | Power features — visual diff + full clone |
| Q4 2026 | Phase 6, 7 | Production — Docker + plugins |
| Q1 2027 | Phase 8, 9, 10 | Platform — multi-user + multi-provider + observability |

---

## 🚫 Out of scope (deliberately)

We will NOT build:
- **Captcha solvers** — legally murky and against most ToS
- **Mass-account creation tools** — clear abuse vector
- **Anonymity / Tor integration** — different problem space
- **Custom browser engine** — Playwright is enough
- **Mobile browser automation** — desktop only

These belong in adjacent projects, not here.

---

## 🔄 How to update this roadmap

When a phase ships:
1. Move it to "Current state" with the actual delivered metrics
2. Update `CHANGELOG.md`
3. Adjust dependent phases if scope shifted
4. Open the next phase's spec doc at `docs/phases/PHASE_N.md`

When a phase is reprioritized, leave the original block in place and add a note:
```
> 🔄 Deferred to Q3 2026 — Phase 5 took priority due to user demand for full-site cloning.
```
