# 🔌 REST + WebSocket API Reference

All endpoints return JSON. WebSocket sends newline-delimited JSON events.

**Base URL:** `http://127.0.0.1:8000`

---

## Authentication

Phase 1: **none** (localhost only). Phase 8 will add JWT + API keys.

---

## 🎯 Task endpoints

### `POST /api/run` — free-form agentic task

```json
{
  "goal": "Find the top 3 trending repos on GitHub today",
  "headless": true,
  "use_vision": false
}
```

**Response:**
```json
{"task_id": "a1b2c3d4ef", "status": "queued"}
```

`headless` and `use_vision` are optional — default from `.env`.

---

### `POST /api/signup` — create an account

```json
{
  "site_url": "https://news.ycombinator.com",
  "full_name": "Alex Reader",
  "extra_instructions": "Use the dispoable email; remember username on success."
}
```

Uses `mail.tm` disposable email under the hood.

---

### `POST /api/login` — log in and (optionally) persist the session

```json
{
  "site_url": "https://github.com/login",
  "email": "user@example.com",
  "password": "hunter2",
  "persist_session": true,
  "profile_name": "github_main"
}
```

When `persist_session=true`, cookies and localStorage are saved to `outputs/profiles/<profile_name>/` — next login reuses them.

---

### `POST /api/explore` — produce a feature/UX report

```json
{
  "site_url": "https://stripe.com",
  "depth_hint": "thorough"
}
```

`depth_hint` ∈ `{"quick", "normal", "thorough"}` — controls how many pages the agent visits.

**Result shape:**
```json
{
  "site": "...",
  "report": {
    "purpose": "...",
    "main_features": [...],
    "key_user_flows": [...],
    "tech_signals": [...],
    "design_notes": {"palette": [...], "typography": "...", "layout": "..."},
    "clone_recipe": [...],
    "risks_or_blockers": [...]
  },
  "report_path": "outputs/reports/stripe.com.json"
}
```

---

### `POST /api/clone` — rebuild a page as clean Tailwind HTML

```json
{
  "url": "https://tailwindcss.com",
  "max_assets": 60
}
```

Output in `outputs/cloned_sites/<domain>/index.html` + assets.

---

## 📊 Inspection endpoints

### `GET /api/tasks` — list all tasks

```json
[
  {
    "task_id": "127af4722a",
    "kind": "explore",
    "params": {...},
    "status": "succeeded",
    "result": {...},
    "error": null
  },
  ...
]
```

### `GET /api/tasks/{id}` — one task

Same shape as above for a single task.

### `GET /api/tasks/{id}/events` — replay all events for a task

```json
[
  {"task_id":"...", "type":"task_start", "data":{...}, "ts": 1721234567.89},
  {"task_id":"...", "type":"plan", "data":{...}},
  ...
]
```

### `DELETE /api/tasks/{id}` — cancel a running task

```json
{"task_id": "...", "status": "cancelled"}
```

### `GET /api/artifact/{task_id}/{filename}` — download a screenshot

Returns `image/png` for files in `outputs/sessions/<task_id>/`.

---

## 📡 WebSocket — `/ws/{task_id}`

Stream of events for one task. Connect immediately after `POST /api/run` (or any task creator).

**Each frame:**
```json
{
  "task_id": "127af4722a",
  "type": "perception",
  "data": {"step": 3, "url": "...", "title": "...", "n_elements": 42, "screenshot": "step_003.png"},
  "ts": 1721234567.89
}
```

**Event types in order:**
1. `task_start`
2. `plan`
3. `perception` (per step)
4. `decision` (per step)
5. `action_result` (per step)
6. `verdict`
7. `task_end`

The socket closes after `task_end`.

---

## 🎬 Action schema (for `decision` events)

Every decision is exactly one of these:

```json
{"action":"goto",    "url":"https://..."}
{"action":"click",   "index": 12}
{"action":"type",    "index": 7, "text":"hello"}
{"action":"press",   "key":"Enter"}
{"action":"scroll",  "direction":"down|up", "amount": 600}
{"action":"wait",    "seconds": 2}
{"action":"extract", "what":"product price"}
{"action":"done",    "summary":"final answer..."}
{"action":"fail",    "reason":"captcha appeared"}
```

`index` references the numbered elements in the previous `perception` event.

---

## 🚨 Error responses

| Status | Meaning |
|---|---|
| `400` | Bad input — pydantic validation failed |
| `404` | Task not found |
| `409` | Task already finished (can't cancel) |
| `429` | Quota exhausted (Phase 8) |
| `500` | Unhandled error — check `outputs/websearchai.log` |

Error shape:
```json
{"detail": "..."}  // FastAPI default
```

---

## 🧪 Examples

### bash / curl

```bash
# kick off
curl -X POST http://127.0.0.1:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"goal":"Search hackernews and bring me the top 3 titles"}'
# → {"task_id":"abc123","status":"queued"}

# poll
curl http://127.0.0.1:8000/api/tasks/abc123 | jq

# live stream (websocat)
websocat ws://127.0.0.1:8000/ws/abc123
```

### PowerShell

```powershell
$task = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/run `
  -ContentType "application/json" `
  -Body '{"goal":"Find the price of the iPhone 17 on apple.com"}'

# poll
$r = Invoke-RestMethod "http://127.0.0.1:8000/api/tasks/$($task.task_id)"
$r.result.summary
```

### Python

```python
import httpx, asyncio, json
import websockets

async def main():
    async with httpx.AsyncClient() as http:
        r = await http.post("http://127.0.0.1:8000/api/run",
                            json={"goal": "Find AI news on HN"})
        task_id = r.json()["task_id"]

    async with websockets.connect(f"ws://127.0.0.1:8000/ws/{task_id}") as ws:
        async for frame in ws:
            evt = json.loads(frame)
            print(evt["type"], "-", evt.get("data", {}).get("step", ""))
            if evt["type"] == "task_end":
                break

asyncio.run(main())
```

---

## 🔍 OpenAPI

Live, interactive docs are available at:

- Swagger UI → `http://127.0.0.1:8000/docs`
- ReDoc → `http://127.0.0.1:8000/redoc`
- JSON schema → `http://127.0.0.1:8000/openapi.json`
