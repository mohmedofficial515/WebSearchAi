# 📁 Project Structure

A map of every directory and what belongs where.

```
WebSearchAi/
│
├── 📄 README.md                  ← Start here
├── 📄 CHANGELOG.md               ← Version history
├── 📄 CONTRIBUTING.md            ← Pointer to docs/CONTRIBUTING.md
├── 📄 LICENSE                    ← MIT
├── 📄 SECURITY.md                ← Vulnerability disclosure
│
├── 📄 pyproject.toml             ← Modern Python packaging + tool configs
├── 📄 requirements.txt           ← Pinned runtime deps (kept for pip-tools fallback)
├── 📄 .env.example               ← Template for required env vars
├── 📄 .gitignore                 ← Standard ignores + outputs/, .venv/
├── 📄 .pre-commit-config.yaml    ← ruff + gitleaks pre-commit hooks
├── 📄 .dockerignore              ← Exclude tests/, docs/, .venv/ from images
│
├── 📄 Dockerfile                 ← Multi-stage build, non-root user
├── 📄 docker-compose.yml         ← Local dev stack
├── 📄 Makefile                   ← Unix dev commands
│
├── 📄 install.bat                ← Windows one-shot setup
├── 📄 start.bat                  ← Launch API + Web UI on Windows
├── 📄 cli.bat                    ← Run CLI commands on Windows
│
├── 📄 serve.py                   ← Uvicorn launcher for the API
├── 📄 run.py                     ← Typer CLI launcher
│
├── 📂 src/                       ← All application code
│   ├── 📄 __init__.py
│   ├── 📄 config.py              ← pydantic-settings, loaded from .env
│   ├── 📄 cli.py                 ← Typer command definitions
│   │
│   ├── 📂 core/                  ← The agent loop primitives (no business logic)
│   │   ├── browser.py            ← Playwright wrapper + stealth
│   │   ├── perception.py         ← DOM walker + screenshots
│   │   ├── planner.py            ← LLM personas: planner + decider
│   │   ├── executor.py           ← JSON action → Playwright call
│   │   ├── verifier.py           ← Did we succeed?
│   │   └── agent.py              ← Orchestrator (Plan→Perceive→Decide→Act→Verify)
│   │
│   ├── 📂 llm/                   ← LLM client
│   │   ├── mistral_client.py     ← Mistral text + Pixtral vision + retries
│   │   └── 📂 providers/         ← Phase 9: multi-provider abstraction (scaffold)
│   │
│   ├── 📂 skills/                ← High-level capabilities (one file per skill)
│   │   ├── signup.py             ← Create accounts via disposable email
│   │   ├── login.py              ← Persistent-session login
│   │   ├── explore.py            ← Walk site → structured feature report
│   │   └── clone.py              ← Rebuild a page as Tailwind HTML
│   │
│   ├── 📂 api/                   ← FastAPI surface
│   │   ├── main.py               ← Endpoints + WebSocket + UI mounting
│   │   └── tasks.py              ← In-memory background task manager
│   │
│   ├── 📂 utils/                 ← Cross-cutting helpers
│   │   ├── logger.py             ← Loguru config
│   │   ├── event_bus.py          ← Async pub/sub for step streaming
│   │   ├── human_behavior.py     ← Bezier mouse + WPM typing + delays
│   │   └── temp_mail.py          ← mail.tm disposable-email client
│   │
│   ├── 📂 storage/               ← Phase 6: durable task storage (scaffold)
│   └── 📂 memory/                ← Phase 2: long-term agent memory (scaffold)
│
├── 📂 web/                       ← Static Web UI (no build step)
│   ├── 📂 templates/index.html   ← Single-page app shell
│   └── 📂 static/
│       ├── style.css             ← Dark theme + CSS vars
│       └── app.js                ← WS client + form handlers
│
├── 📂 tests/                     ← pytest suite
│   ├── conftest.py               ← FakeLLM, tmp-output fixtures
│   ├── 📂 unit/                  ← Hermetic, < 5s total
│   │   ├── test_config.py
│   │   ├── test_event_bus.py
│   │   ├── test_planner.py
│   │   ├── test_verifier.py
│   │   └── test_executor.py
│   ├── 📂 integration/           ← Real Playwright against httpbin
│   │   └── test_browser_smoke.py
│   └── 📂 fixtures/              ← Static HTML/JSON for offline tests
│
├── 📂 docs/                      ← All documentation
│   ├── ROADMAP.md                ← 10-phase plan with effort + acceptance
│   ├── ARCHITECTURE.md           ← Components + data flow + contracts
│   ├── API.md                    ← REST + WebSocket reference
│   ├── SKILLS.md                 ← How to write a new skill
│   ├── CONFIGURATION.md          ← All .env knobs explained
│   ├── DEPLOYMENT.md             ← Docker / Fly / Cloud Run / k8s
│   ├── CONTRIBUTING.md           ← Dev workflow + PR checklist
│   ├── TROUBLESHOOTING.md        ← Common errors + fixes
│   └── PROJECT_STRUCTURE.md      ← This file
│
├── 📂 scripts/                   ← Developer utilities
│   ├── dev.ps1                   ← Windows PowerShell dev helper
│   ├── smoke_test.py             ← End-to-end server health check
│   └── new_skill.py              ← Scaffold a new skill from template
│
├── 📂 .github/
│   ├── 📂 workflows/
│   │   ├── ci.yml                ← Lint + unit + integration + Docker
│   │   └── release.yml           ← Tag → ghcr.io image + GitHub Release
│   ├── 📂 ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
│
└── 📂 outputs/                   ← Runtime state (gitignored)
    ├── 📂 sessions/<task_id>/    ← Per-task screenshots + result.json
    ├── 📂 reports/               ← Explore reports
    ├── 📂 cloned_sites/          ← Clone outputs
    ├── 📂 screenshots/           ← Ad-hoc captures
    ├── 📂 profiles/              ← Persistent browser profiles
    ├── 📄 memory.db              ← Phase 2 SQLite store
    └── 📄 websearchai.log        ← Rolling app log
```

---

## 🧭 Decision tree: "where do I put new code?"

```
Did the user request a new capability (e.g. "scrape X")?
│
├── It involves browsing + LLM → src/skills/<name>.py
│   (then expose via src/api/main.py and src/cli.py)
│
├── It's a new browser primitive (a new gesture, a new wait condition)?
│   └── src/core/browser.py or src/core/executor.py
│
├── It's a new LLM persona/prompt?
│   └── src/core/planner.py or new src/core/<persona>.py
│
├── It's a cross-cutting utility (logging, retries, parsing)?
│   └── src/utils/<name>.py
│
├── It's a new LLM provider?
│   └── src/llm/providers/<name>.py  (Phase 9)
│
├── It's persistent storage?
│   └── src/storage/<name>.py        (Phase 6)
│
├── It's agent memory?
│   └── src/memory/<name>.py         (Phase 2)
│
└── It's a one-off script?
    └── scripts/<name>.py
```

---

## 📊 Module size guidelines

Soft limits to keep files reviewable:

| Layer | Soft cap | Hard cap |
|---|---|---|
| `core/*.py` | 150 lines | 300 |
| `skills/*.py` | 200 lines | 400 |
| `api/*.py` | 250 lines | 500 |
| `utils/*.py` | 100 lines | 200 |

If a file is approaching the hard cap, that's a sign it should split. Example: `skills/clone.py` could grow into `skills/clone/{capture.py,rewrite.py,rebuild.py}`.

---

## 🚫 What does NOT live in this repo

- **Built browser binaries** — `python -m playwright install chromium` fetches them
- **Trained models** — we don't train anything; LLM lives at Mistral
- **Site clones produced by the tool** — those go in `outputs/cloned_sites/` (gitignored)
- **API keys** — `.env` is gitignored; `.env.example` shows the shape
