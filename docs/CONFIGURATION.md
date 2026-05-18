# ⚙️ Configuration Reference

All configuration lives in `.env` (loaded by `src/config.py` via `pydantic-settings`). Copy `.env.example` to `.env` and edit.

---

## 🔐 LLM (Mistral)

| Key | Default | What it does |
|---|---|---|
| `MISTRAL_API_KEY` | **required** | Free key from <https://console.mistral.ai/> |
| `MISTRAL_TEXT_MODEL` | `mistral-small-latest` | Free text model — used for planning, deciding, verifying |
| `MISTRAL_VISION_MODEL` | `pixtral-12b-2409` | Free vision model — used when `use_vision=true` |

**Free tier limits (as of 2026):**
- 1 request / second on free models
- ~500K tokens / month
- One average task ≈ 3K–8K tokens → ~60–150 tasks / month

---

## 🌐 Browser

| Key | Default | What it does |
|---|---|---|
| `BROWSER_HEADLESS` | `false` | Hide (`true`) or show (`false`) the Chromium window |
| `BROWSER_TYPE` | `chromium` | `chromium`, `firefox`, or `webkit` |
| `BROWSER_TIMEOUT` | `30000` | Default selector wait, in milliseconds |
| `BROWSER_VIEWPORT_WIDTH` | `1366` | Viewport width in pixels |
| `BROWSER_VIEWPORT_HEIGHT` | `768` | Viewport height in pixels |

### Headless on, but want screenshots?
That's the default — `BROWSER_HEADLESS=true` still captures screenshots and streams them to the Web UI.

### When to choose Firefox or WebKit
- **Firefox** — when a site blocks Chromium specifically
- **WebKit** — when you need Safari-like rendering for testing

Note: stealth is most battle-tested on Chromium.

---

## 🥷 Stealth & cadence

| Key | Default | What it does |
|---|---|---|
| `ENABLE_STEALTH` | `true` | Inject the anti-detection JS init script |
| `MIN_ACTION_DELAY_MS` | `300` | Lower bound of random delay after each action |
| `MAX_ACTION_DELAY_MS` | `1200` | Upper bound of random delay |
| `HUMAN_TYPING_WPM` | `240` | Words-per-minute typing simulation |

**Tuning tips:**
- For sites that aggressively rate-limit, raise `MAX_ACTION_DELAY_MS` to `3000`+.
- For trusted internal sites where speed matters, drop both delays to `100`/`300`.

---

## 🤖 Agent loop

| Key | Default | What it does |
|---|---|---|
| `MAX_STEPS_PER_TASK` | `40` | Hard cap on steps before the loop exits |
| `MAX_RETRIES_PER_STEP` | `3` | LLM call retries within one step |

If you see "Planner could not produce a valid action" — bump `MAX_RETRIES_PER_STEP` to 5, or the LLM is too small / too rate-limited.

---

## 🚀 API server

| Key | Default | What it does |
|---|---|---|
| `API_HOST` | `127.0.0.1` | Use `0.0.0.0` to bind all interfaces |
| `API_PORT` | `8000` | TCP port |

⚠️ **Don't bind 0.0.0.0 on a public IP without authentication** (Phase 8 will add JWT).

---

## 📁 Storage

| Key | Default | What it does |
|---|---|---|
| `OUTPUT_DIR` | `./outputs` | Root for sessions, reports, profiles, logs |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Layout under `OUTPUT_DIR`:
```
sessions/<task_id>/*.png + result.json
reports/<site>.json
cloned_sites/<domain>/
profiles/<profile_name>/      ← persistent browser profiles
screenshots/                  ← ad-hoc captures
memory.db                     ← Phase 2
websearchai.log              ← rotating app log
```

---

## 🌍 Network

| Key | Default | What it does |
|---|---|---|
| `HTTP_PROXY` | _(unset)_ | Routes browser traffic through a proxy. Format: `http://user:pass@host:port` |

Use cases:
- Geo-restricted content
- Residential proxies for sites that block datacenter IPs
- Recording traffic via mitmproxy

---

## 🧪 Example `.env`

```dotenv
# Required
MISTRAL_API_KEY=your_key_here

# Browser
BROWSER_HEADLESS=true
ENABLE_STEALTH=true

# Cadence — tune up if rate-limited
MIN_ACTION_DELAY_MS=400
MAX_ACTION_DELAY_MS=1500
HUMAN_TYPING_WPM=220

# Agent
MAX_STEPS_PER_TASK=40
MAX_RETRIES_PER_STEP=3

# Server
API_HOST=127.0.0.1
API_PORT=8000

# Storage
OUTPUT_DIR=./outputs
LOG_LEVEL=INFO

# Optional
# HTTP_PROXY=http://user:pass@proxy.example.com:8080
```

---

## 🔬 Debug mode

For verbose troubleshooting:

```dotenv
LOG_LEVEL=DEBUG
BROWSER_HEADLESS=false   # watch the browser do its thing
```

Then tail the log:

```bash
tail -f outputs/websearchai.log
```

---

## 🎚️ Per-task overrides

The REST API accepts per-task overrides for the most common knobs:

```json
POST /api/run
{
  "goal": "...",
  "headless": false,      // overrides BROWSER_HEADLESS for this task
  "use_vision": true      // forces Pixtral vision on
}
```

`signup`, `login`, `explore`, `clone` accept similar per-task params — see `docs/API.md`.
