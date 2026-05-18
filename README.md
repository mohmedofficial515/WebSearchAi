# 🌐 WebSearchAi

**Professional AI-driven browser automation.** Give it a natural-language goal — it drives a real browser like a human, sees pages with vision AI, extracts what you asked for, and reports back.

Built on **Mistral AI** (free tier) + **Playwright** + **FastAPI**.

<p align="center">
  <a href="docs/ROADMAP.md">Roadmap</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/API.md">API</a> ·
  <a href="docs/SKILLS.md">Skills</a> ·
  <a href="docs/CONFIGURATION.md">Config</a> ·
  <a href="docs/DEPLOYMENT.md">Deploy</a> ·
  <a href="docs/TROUBLESHOOTING.md">Troubleshoot</a>
</p>

---

## ✨ Capabilities

| Skill | What it does |
|---|---|
| 🎯 **Run** | Free-form goal → autonomous browsing (search, click, type, extract) |
| 📝 **Signup** | Create an account on any site (uses free disposable email) |
| 🔑 **Login** | Log in with credentials, persist session for reuse |
| 🔍 **Explore** | Walk a site like a human → structured feature / UX / tech report |
| 📦 **Clone** | Capture a page + AI-rebuild it as clean responsive Tailwind HTML |

Surfaces:
- **Web UI** at `http://127.0.0.1:8000`
- **REST API** at `/api/*` ([reference](docs/API.md))
- **WebSocket** at `/ws/{task_id}` for live progress
- **CLI** — `python run.py <command>` or `cli.bat <command>` on Windows

---

## 🚀 Quick start

### Windows

```powershell
.\install.bat       # creates .venv, installs deps, downloads Chromium
# Edit .env and paste your free Mistral key from https://console.mistral.ai/
.\start.bat         # → http://127.0.0.1:8000
```

### Unix / macOS

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env     # add MISTRAL_API_KEY
python serve.py          # → http://127.0.0.1:8000
```

### Docker

```bash
docker compose up -d     # → http://localhost:8000
docker compose logs -f app
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for production setups.

---

## 🧠 Architecture in one diagram

```
Web UI / CLI / REST
         │
         ▼
   ┌──────────────────┐
   │   Agent Loop     │   Plan → Perceive → Decide → Act → Verify
   └──────────────────┘
    │              │
    ▼              ▼
 Mistral LLM    Playwright
(text+vision)  (Chromium + stealth)
```

Each step emits a typed event on an async bus → consumed live by the Web UI over WebSocket and persisted to `outputs/sessions/<task_id>/`.

Full breakdown: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🗂️ Project layout

```
WebSearchAi/
├── src/
│   ├── core/         ← agent loop primitives (browser, perception, planner, executor, verifier, agent)
│   ├── llm/          ← Mistral client (+ providers/ scaffold for Phase 9)
│   ├── skills/       ← run, signup, login, explore, clone
│   ├── api/          ← FastAPI + WebSocket + task manager
│   ├── utils/        ← logger, event_bus, human_behavior, temp_mail
│   ├── storage/      ← Phase 6 scaffold (durable task store)
│   ├── memory/       ← Phase 2 scaffold (long-term agent memory)
│   ├── cli.py        ← Typer CLI
│   └── config.py     ← pydantic-settings
├── web/              ← static SPA (no build step)
├── tests/            ← unit/ + integration/ pytest suites
├── docs/             ← ROADMAP, ARCHITECTURE, API, SKILLS, …
├── scripts/          ← dev helpers (new_skill.py, smoke_test.py)
├── .github/          ← CI workflows + issue/PR templates
└── outputs/          ← runtime artifacts (gitignored)
```

Full map with size guidelines: [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md).

---

## 🔌 REST API at a glance

```bash
# Free-form task
curl -X POST http://127.0.0.1:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"goal":"Find AI news on HackerNews"}'
# → {"task_id":"a1b2c3d4ef","status":"queued"}

# Structured site analysis
curl -X POST http://127.0.0.1:8000/api/explore \
  -H "Content-Type: application/json" \
  -d '{"site_url":"https://stripe.com"}'

# Inspect or live-stream
curl http://127.0.0.1:8000/api/tasks/a1b2c3d4ef
# ws://127.0.0.1:8000/ws/a1b2c3d4ef
```

Interactive docs: `/docs` (Swagger) · `/redoc` (ReDoc). Full reference: [`docs/API.md`](docs/API.md).

---

## ⚙️ Configuration

Copy `.env.example` → `.env` and edit. Required:

```dotenv
MISTRAL_API_KEY=your_free_key_here
```

Common knobs (see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full list):

| Key | Default | Effect |
|---|---|---|
| `BROWSER_HEADLESS` | `false` | Hide/show the browser window |
| `ENABLE_STEALTH` | `true` | Inject anti-detection JS |
| `MAX_STEPS_PER_TASK` | `40` | Hard cap on agent steps |
| `HUMAN_TYPING_WPM` | `240` | Typing speed simulation |
| `HTTP_PROXY` | — | Route browser traffic via proxy |

---

## 🛣️ Roadmap

Phase 1 (MVP) is shipped. Next:

- **Phase 2** — long-term memory + skill library
- **Phase 3** — multi-tab / parallel orchestration
- **Phase 4** — visual diff & regression testing
- **Phase 5** — full multi-page site cloning
- **Phase 6** — Docker + remote agent runner + Redis queue
- **Phase 7** — plugin system for third-party skills
- **Phase 8** — auth + multi-user + quotas
- **Phase 9** — LLM provider abstraction (OpenAI, Anthropic, Ollama)
- **Phase 10** — production observability (OTel, Prometheus, Grafana)

Detailed plan with acceptance criteria and effort estimates: [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## 🧪 Development

```bash
make install-dev          # or:  ./scripts/dev.ps1 install  (Windows)
make test                 # unit tests
make test-integration     # real browser, uses httpbin.org
make lint                 # ruff + mypy
make format               # auto-fix
```

New skill in 30 seconds:

```bash
python scripts/new_skill.py review_amazon_product
# → src/skills/review_amazon_product.py + tests/integration/test_review_amazon_product.py
```

Walkthrough: [`docs/SKILLS.md`](docs/SKILLS.md). Contributor guide: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

---

## ⚠️ Legal & ethics

This is a neutral browser automation framework. **You are responsible for how you use it.**

- ✅ Test your own sites · scrape public data · analyze public competitor UX · prototype clones for learning
- ❌ Don't violate ToS · brute-force accounts · scrape private data · republish copyrighted content

We deliberately don't ship captcha solvers, IP rotators, or mass-account tools — see [`docs/ROADMAP.md` § Out of scope](docs/ROADMAP.md#-out-of-scope-deliberately).

Security reports: [`SECURITY.md`](SECURITY.md).

---

## 📜 License

MIT — see [`LICENSE`](LICENSE).
