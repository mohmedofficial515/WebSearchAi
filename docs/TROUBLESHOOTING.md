# 🔧 Troubleshooting

The most common things that go wrong, and how to fix them fast.

---

## 🔴 The browser

### "Playwright executable doesn't exist"
```
playwright._impl._errors.Error: Executable doesn't exist at .../chromium-*/chrome.exe
```

**Fix:**
```bash
python -m playwright install chromium
```

### Sec-Ch-Ua leaks "HeadlessChrome"

Symptom: site detects you as a bot even with stealth on. Check the `Sec-Ch-Ua` header in network logs.

**Fix:** confirmed in `src/core/browser.py:86-96` — make sure that override block is intact. If you tweaked it, the override only applies to the **non-persistent** branch. For `launch_persistent_context`, Chromium doesn't accept `extra_http_headers` in launch_kwargs — pass it via `set_extra_http_headers` after the page opens.

### Browser closes immediately

Usually a Chromium crash. Check:
- Disk space (Chromium needs ~200 MB free for tmp files)
- Add `--disable-dev-shm-usage` to launch args (already there in `core/browser.py:67`)
- On Docker: `--shm-size=2gb`

---

## 🧠 The LLM (Mistral)

### `429 Too Many Requests`

You hit the free tier rate limit (1 req/sec).

**Fix:** the `MistralClient` already has tenacity retries with exponential backoff. If you see this often:
- Reduce `MAX_RETRIES_PER_STEP` (each retry is another call)
- Use vision **only on attempt 0** (already the default)
- Upgrade to Mistral pay-as-you-go

### `401 Unauthorized`

Your API key is wrong, expired, or not loaded.

**Fix:**
```bash
# Verify .env loads
python -c "from src.config import settings; print(settings.mistral_api_key[:8])"
```

If empty: check `.env` exists in the project root and pydantic-settings is reading it.

### Decisions return `{"action": "fail", "reason": "Planner could not produce a valid action"}`

The decider couldn't return valid JSON across 3 retries. Possible causes:
- Mistral returned conversational prose ("Sure, here's…")  → bump `MAX_RETRIES_PER_STEP` to 5
- The page snapshot is too big — see "Token limit" below
- The model is overloaded — retry the task

### Token limit exceeded

Symptom: long error mentioning `context_length` or `400`.

**Fix:** in `core/perception.py`, the `render_for_llm` already caps elements at 80. If you're slamming the cap, lower it:
```python
snap_text = snap.render_for_llm(max_elements=50)
```

---

## 🤖 The agent loop

### Agent keeps clicking the same element

Loop detection isn't implemented yet. Workaround: tighten the goal:

```
Bad: "Find me an article about X"
Good: "Find me an article about X. If you visit a search result that doesn't contain X, go back and try a different result."
```

### Agent extracts the same data three times

Fixed in `core/planner.py:54`:
> "Do NOT repeat an 'extract' action if the ACTION HISTORY already shows a successful extraction from the same page — emit 'done' instead."

If you see this regression, that rule got stripped.

### Verifier says success=false even though the data is right there

Fixed in `core/verifier.py` + `core/agent.py:146-152`: extractions are now passed as primary evidence.

If you see this: confirm `Agent._run_loop` calls `verifier.verify(..., extractions=extractions)` not just snapshot text.

---

## 🌐 The Web UI

### WebSocket disconnects immediately
- Make sure the task_id in the URL matches a real task (check `GET /api/tasks`)
- Check browser console for errors
- Reverse proxy? Increase `proxy_read_timeout`

### Screenshots don't appear in the live view
- Check `outputs/sessions/<task_id>/` has PNG files
- Check the `screenshot` field in the `perception` event
- The artifact endpoint serves them: `GET /api/artifact/<task_id>/step_001.png`

### Task list is empty after restart
Expected — the in-memory task store doesn't persist. Phase 6 adds Redis backing.

---

## 🚦 CAPTCHAs and bot challenges

If the agent hits Cloudflare/hCaptcha/etc, it emits:

```json
{"action": "fail", "reason": "Encountered Cloudflare security verification..."}
```

**This is correct behavior.** We don't solve captchas (out of scope — see `docs/ROADMAP.md`).

**Workarounds for legitimate use:**
1. Use a residential proxy via `HTTP_PROXY`
2. Run with `BROWSER_HEADLESS=false` and `enable_stealth=true` (less detectable)
3. Pre-warm a profile with manual login, then point the agent at the persisted profile

---

## 📁 Output / disk

### `outputs/` grows huge

Each task can leave 10-40 screenshots. Cleanup:

```powershell
# Windows: delete sessions older than 7 days
Get-ChildItem outputs/sessions -Directory |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
  Remove-Item -Recurse -Force
```

```bash
# Unix: same
find outputs/sessions -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
```

### Log file ballooning
Edit `src/utils/logger.py` to add a `RotatingFileHandler`:
```python
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
```

---

## 🛠️ Development gotchas

### "Module not found" errors
Run `pip install -e .` (editable install) or run scripts via `python -m src.cli` not `python src/cli.py`.

### Hot reload doesn't work
`uvicorn --reload` doesn't pick up Playwright's child processes well. After editing `core/` or `skills/`, restart the server fully:

```bash
# Windows
taskkill /F /IM python.exe
python serve.py
```

### Tests fail with "asyncio.exceptions.CancelledError"
Almost always one test forgot `await agent.session.stop()`. Use `async with Agent() as agent:` not bare construction.

---

## 🆘 Still stuck?

1. Re-run with `LOG_LEVEL=DEBUG` and `BROWSER_HEADLESS=false`
2. Watch what happens visually + tail `outputs/websearchai.log`
3. Open a GitHub issue with logs, screenshots, and the exact goal you gave the agent
