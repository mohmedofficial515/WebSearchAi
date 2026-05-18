# 🛠️ Writing a New Skill

A **skill** is a high-level capability built on top of the agent loop. The existing five skills (`run`, `signup`, `login`, `explore`, `clone`) all follow the same pattern.

This guide walks you through writing your own.

---

## 🧠 What is a skill?

A skill is a Python coroutine that:
1. Constructs a precise goal string for the agent
2. (Optionally) prepares external resources — a disposable email, a profile dir, a starting dataset
3. Calls `Agent.run(goal)`
4. (Optionally) post-processes the result — turning raw extractions into a structured report

The agent loop does the heavy lifting; the skill is glue + domain knowledge.

---

## 📐 Skill anatomy

```python
# src/skills/<your_skill>.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..core.agent import Agent
from ..llm.mistral_client import MistralClient


@dataclass
class YourResult:
    field_a: str
    field_b: dict


async def your_skill(arg1: str, arg2: int = 10) -> YourResult:
    # 1. Build the goal — the more specific, the cheaper.
    goal = (
        f"Visit {arg1}. Do X, Y, Z.\n"
        "End with a 'done' action whose summary lists what you found."
    )

    # 2. Run the agent
    async with Agent() as agent:
        result = await agent.run(goal)

    # 3. Post-process (optional)
    llm = MistralClient()
    try:
        report = await llm.chat_json(SYSTEM_PROMPT, result.summary)
    finally:
        await llm.close()

    # 4. Persist
    out = Path(settings.output_path) / "your_skill" / f"{arg1}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    return YourResult(field_a=arg1, field_b=report)
```

---

## ✅ Step-by-step

### 1. Pick a good goal

Goals are LLM prompts. The agent will follow them literally. Bad goals waste steps.

**Bad:**
> "go to amazon and find something"

**Good:**
> "Visit https://amazon.com. Search for 'wireless mouse'. Open the first organic (non-sponsored) result. Extract the product title, price, rating, and number of reviews. End with a 'done' action whose summary contains exactly: TITLE | PRICE | RATING | REVIEWS."

The second goal:
- Has a clear starting URL
- Specifies the query
- Disambiguates "organic vs sponsored"
- Lists the exact fields to extract
- Tells the agent how to format the answer

### 2. Decide if you need post-processing

For freeform tasks: `result.summary` is your answer.

For structured output (a JSON report, a table, a chart-ready dataset): make a second LLM call after the agent finishes. This is what `explore` and `clone` do.

```python
REPORT_SYSTEM = """You are a careful data extractor.
You receive a browser-agent transcript. Output JSON:
{"field_a": "...", "field_b": [...]}
"""

report = await llm.chat_json(REPORT_SYSTEM, json.dumps(result.to_dict()))
```

### 3. Expose the skill

Wire it up in three places:

**a. CLI** — `src/cli.py`:
```python
@app.command()
def yourskill(arg1: str, arg2: int = 10):
    """One-line description shown in --help."""
    asyncio.run(your_skill(arg1, arg2))
```

**b. REST API** — `src/api/main.py`:
```python
class YourSkillParams(BaseModel):
    arg1: str
    arg2: int = 10

@app.post("/api/yourskill")
async def yourskill_endpoint(params: YourSkillParams):
    return await tasks.submit("yourskill", params.model_dump(), runner=your_skill)
```

**c. Web UI** (optional) — add a tab in `web/templates/index.html` + handler in `web/static/app.js`.

### 4. Test it

Write at least one test in `tests/integration/test_your_skill.py`:

```python
import pytest

@pytest.mark.asyncio
async def test_your_skill_happy_path():
    result = await your_skill("https://httpbin.org/get")
    assert result.field_a
    assert "args" in result.field_b
```

Use `httpbin.org` for deterministic targets. Avoid testing against real third-party sites in CI — they'll break flakily.

---

## 🎨 Common patterns

### Pattern 1: Use an external resource

```python
from ..utils.temp_mail import TempMailbox

async def signup_with_disposable_email(site_url: str) -> SignupResult:
    inbox = TempMailbox()
    await inbox.start()
    try:
        goal = f"Visit {site_url}, sign up with email {inbox.address}. ..."
        async with Agent() as agent:
            result = await agent.run(goal)

        # Wait for verification email
        link = await inbox.wait_for_link(timeout=120)
        if link:
            # Have the agent click the verification link
            ...
    finally:
        await inbox.close()
```

### Pattern 2: Persist a browser profile

```python
from pathlib import Path

async def login_persistent(site, email, password, profile_name):
    profile_dir = Path("outputs/profiles") / profile_name

    async with Agent(user_data_dir=profile_dir) as agent:
        result = await agent.run(f"Log into {site} with {email}/{password}...")
        # Next login with the same profile_name will reuse cookies
```

### Pattern 3: Multi-step skill (chain agent calls)

```python
async def research_then_summarize(topic: str) -> ResearchResult:
    # Stage 1: find sources
    async with Agent() as agent:
        sources = await agent.run(
            f"Find 5 reputable URLs about '{topic}'. "
            "End with done and a JSON list of URLs in the summary."
        )

    urls = parse_urls_from(sources.summary)

    # Stage 2: visit each
    summaries = []
    async with Agent() as agent:
        for url in urls:
            r = await agent.run(f"Visit {url}, extract main points...")
            summaries.append(r.summary)

    # Stage 3: synthesize
    llm = MistralClient()
    final = await llm.chat(SYSTEM_SYNTH, "\n\n".join(summaries))
    await llm.close()

    return ResearchResult(topic=topic, sources=urls, synthesis=final)
```

---

## 🚫 Anti-patterns

### Don't: instantiate Playwright directly

```python
# ❌ bad
from playwright.async_api import async_playwright
pw = await async_playwright().start()
```

Always go through `BrowserSession` (which `Agent` owns). Otherwise you bypass stealth, telemetry, and event emission.

### Don't: call the LLM in a tight loop

```python
# ❌ bad — 100 LLM calls
for item in items:
    classified = await llm.chat(prompt, item)
```

Batch in one prompt:

```python
# ✅ good — 1 LLM call
classified = await llm.chat_json(prompt, json.dumps(items))
```

### Don't: swallow exceptions in the skill layer

```python
# ❌ bad
try:
    result = await agent.run(goal)
except Exception:
    return None
```

Let it propagate. The `TaskManager` wraps the skill in a try/except and stores `status=failed` with the error — that's where errors belong.

### Don't: write to stdout

Use `from ..utils.logger import log`. The logger writes to both file and console with proper levels.

---

## 🎯 Skill quality checklist

Before merging a new skill:

- [ ] Goal string is specific and testable
- [ ] Has at least one passing integration test against `httpbin.org` or a static fixture
- [ ] Exposed via CLI, REST, and (if user-facing) Web UI
- [ ] Output written to `outputs/<skill>/` with a stable filename scheme
- [ ] No direct Playwright imports
- [ ] No `print()` calls — uses `log`
- [ ] Documented in `docs/SKILLS.md` (this file) and `README.md`
- [ ] Handles `agent.run()` returning `success=False` gracefully

---

## 🔮 Coming in Phase 7 — Plugin System

Once the plugin loader ships, you'll be able to drop a skill file in `~/.websearchai/plugins/` without touching the main repo. The contract above will stay the same; we'll just add a small `Skill` Protocol class for type-safe discovery.
