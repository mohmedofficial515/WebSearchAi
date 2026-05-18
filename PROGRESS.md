# WebSearchAi — Chat UI Implementation Progress

> Branch: `feat/agentic-research-arabic-reports`
> Plan file: `CHAT_UI_PLAN.md` (v3 HARDENED — 9 phases, 62 tasks, 30 rules, 10 ADRs)
> Last updated: 2026-05-18

---

## Quick Status

| Phase | Name | Tasks | Status |
|---|---|---|---|
| **A** | Scaffolding | 10 | ✅ COMPLETE |
| **B** | Backend additions + prompt extraction | 17 | ✅ COMPLETE |
| **C** | Core chat shell | 23 | ✅ COMPLETE |
| **D** | Existing skill cards (10) | 11 | ✅ COMPLETE |
| **E** | Pipeline UI | 7 | ✅ COMPLETE |
| **F** | New skills (8) | 9 | ✅ COMPLETE |
| **G** | Settings + attachments | 7 | ⬜ Pending |
| **H** | Migration cutover | 11 | ⬜ Pending |
| **I** | Polish | 8 | ⬜ Pending |

**Overall progress: 77 / 103 tasks complete**

> Phase F verified 2026-05-18:
> - TSC: 0 errors (strict mode)
> - Backend skills: md_writer, html_artifact, code_artifact, mermaid_diagram, summarize, translate, competitor_matrix
> - pdf_export reuses md_writer backend + client-side print-to-PDF
> - chat.py _dispatch_single: 8 new skill handlers added
> - Frontend cards: MarkdownArtifactCard (react-markdown+GFM+KaTeX), HtmlArtifactCard (iframe CSP sandbox)
> - CodeArtifactCard (shiki highlighting + copy + download)
> - MermaidArtifactCard (mermaid.js SVG render + download SVG)
> - PdfArtifactCard (rendered markdown + browser print dialog)
> - SummarizeCard (Arabic summary + bullets + word-count delta %)
> - TranslateCard (side-by-side RTL/LTR bilingual layout)
> - CompetitorMatrixCard (sortable/filterable table + CSV BOM download)
> - ChatThread.tsx: routes 8 new skills by name
> - Next: **'ابدأ Phase G'** to build Settings + attachments

> Phase E verified 2026-05-18:
> - TSC: 0 errors (strict mode)
> - usePipeline.ts: full pipeline WS hook (plan/step_start/step_end/paused/resumed/end events)
> - PipelineStep.tsx: step icon + status dot + MiniStream live expand
> - PipelineApproval.tsx: [▶ تشغيل] [✕ إلغاء] with POST to /api/pipelines/{id}/approve|cancel
> - PipelinePausedForm.tsx: inline required_fields form → POST /api/pipelines/{id}/resume
> - PipelineCard.tsx: full pipeline card orchestrating all pipeline sub-components
> - ChatThread.tsx: routes pipelineId messages to PipelineCard
> - ChatPage.tsx: handles mode=pipeline + mode=need_params from /api/chat
> - api.ts ChatResponse: added pipeline? + intent? fields
> - types.ts Message: added pipelineData? field
> - Next: **'ابدأ Phase F'** to build new skill cards

> Phase D verified 2026-05-18:
> - TSC: 0 errors (strict mode)
> - 9 new skill card components: SearchResultCard, ExploreReportCard, DesignTokensCard,
>   ComponentsGalleryCard, LoginCard, SignupCard, TempSignupCard, CloneCard, SiteCloneCard
> - useTaskStream extended: skillResult field + status event handler + task_end normalization
> - ChatThread now routes to correct card by skill prop (switch on 10 skill types)
> - chat.py updated: _emit_skill_result after each skill completes
> - Next: **'ابدأ Phase E'** to build Pipeline UI

> Phase C verified 2026-05-18:
> - TSC: 0 errors (strict mode + noUnusedLocals/Params)
> - Dev server: http://localhost:5174/chat/ returns React app (dir=rtl, lang=ar)
> - 32 files, 2057 insertions — commit 00b079a
> - Next: **'ابدأ Phase D'** to build the 10 skill cards

> Phase B verified 2026-05-18:
> - 12 new endpoints all return non-404 on live server (verified on :8011)
> - Arabic 404 messages render correctly (RULE-27)
> - Full unit suite: 270 passed, 0 failed
> - Prompts moved from inline strings to `prompts/*.md` for: planner, decider,
>   critic (4 sections), synthesizer (2 sections), verifier, explore, clone,
>   find_components, orchestrator, continuation

---

## Setup on a New Machine

### Prerequisites

- Python 3.11+
- Node.js 20+ (LTS)
- Git

### 1. Clone and install

```bash
git clone <repo-url>
cd WebSearchAi
git checkout feat/agentic-research-arabic-reports

# Python deps
pip install -r requirements.txt

# Frontend deps (already committed in web-chat/)
cd web-chat
npm install
cd ..
```

### 2. Environment variables

Copy `.env.example` to `.env` and fill in API keys (Claude, etc.).

### 3. Verify Phase A works

```bash
# In terminal 1 — build the React app
cd web-chat && npm run build

# In terminal 2 — start FastAPI
cd .. && python -m uvicorn src.api.main:app --reload --port 8000

# Browser: http://localhost:8000/chat should show the React app in Arabic/RTL
```

### 4. Dev workflow

```bash
# Start both at once:
cd web-chat && npm run dev          # Vite dev server → http://localhost:5173/chat
python -m uvicorn src.api.main:app --reload --port 8000  # FastAPI
```

The Vite dev server proxies `/api → :8000` and `/ws → ws://localhost:8000`.

---

## Phase A — COMPLETE ✅

**Commit:** `960b572 feat(phase-A): scaffold React/Vite chat SPA with RTL, Tailwind, shadcn primitives`

All 10 tasks done:

- [x] A-01 Vite + React + TS project at `web-chat/`
- [x] A-02 All frontend deps installed
- [x] A-03 `vite.config.ts` — `base: '/chat/'`, proxy, `outDir: '../web/static/chat'`
- [x] A-04 `tsconfig.app.json` — strict TS, `@/*` path alias (TS 6 without baseUrl)
- [x] A-05 `tailwind.config.ts` + `globals.css` — RTL, Arabic/Latin/Mono fonts
- [x] A-06 shadcn/ui primitives (manual setup — CLI failed): Button, Card, Badge, Dialog, Tabs, Tooltip, ScrollArea, Separator
- [x] A-07 `index.html` — `<html lang="ar" dir="rtl">`, Tajawal preconnect
- [x] A-08 FastAPI `/chat` mount in `src/api/main.py` (StaticFiles + SPA fallback)
- [x] A-09 Placeholder `ChatPage.tsx` ("جاري البناء…")
- [x] A-10 Browser verified: `GET http://localhost:8000/chat` → 200, RTL, Tajawal font

**Key technical notes for Phase A:**
- shadcn CLI v4.7.0 failed (workspace config error) → all components written manually in `web-chat/src/components/ui/`
- TypeScript 6.0: `baseUrl` is deprecated — removed it entirely. `paths` works without it in `bundler` moduleResolution mode
- `@import` must come BEFORE `@tailwind` in globals.css (PostCSS requirement)
- `@radix-ui/react-badge` does not exist — Badge implemented manually with CVA

---

## Phase B — NEXT ⏳

> Start by telling Claude: **"ابدأ Phase B"**
>
> All 17 tasks must be done in order. Each task needs a separate `git commit`.
> Commit format: `feat(phase-B): implement <component> — <description>`

### B-01 Create `prompts/` directory + extract planner prompt

**Files:**
- CREATE `prompts/planner.md` — English, contains `{locale}` token
- UPDATE `src/core/planner.py` — replace inline SYSTEM_PROMPT with `load_prompt("planner", locale)`

**Blocking check:** Server restarts without ImportError; planner still works

---

### B-02 Extract decider + critic + perception prompts

**Files:**
- CREATE `prompts/decider.md` — from `src/core/agent.py` (decider system prompt + action schema)
- CREATE `prompts/critic.md` — from `src/core/critic.py`
- UPDATE `src/core/agent.py`, `src/core/critic.py`, `src/core/perception.py`

**Note:** `perception.py` snapshot prompt goes into `prompts/decider.md` as a section.

**Blocking check:** Existing `/api/run` still works end-to-end.

---

### B-03 Extract synthesizer + verifier prompts

**Files:**
- CREATE `prompts/synthesizer.md` — from `src/core/search_agent.py` (synthesis + ranking prompts)
- CREATE `prompts/verifier.md` — from `src/core/verifier.py`
- UPDATE `src/core/search_agent.py`, `src/core/verifier.py`

**Blocking check:** Research skill still returns cited synthesis.

---

### B-04 Extract skill-specific prompts

**Files:**
- CREATE `prompts/skills/explore.md`
- CREATE `prompts/skills/find_components.md`
- CREATE `prompts/skills/design_tokens.md`
- CREATE `prompts/skills/clone.md`
- UPDATE `src/skills/explore.py`, `find_components.py`, `design_tokens.py`, `clone.py`

**Blocking check:** Each skill still produces correct output.

---

### B-05 Write `src/core/prompt_loader.py`

```python
# src/core/prompt_loader.py
from pathlib import Path
_BASE = Path(__file__).parent.parent.parent / "prompts"

def load_prompt(name: str, locale: str = "ar", **kwargs) -> str:
    path = _BASE / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    template = path.read_text(encoding="utf-8")
    return template.format(locale=locale, **kwargs)
```

**Blocking check:** `tests/test_prompt_loader.py` passes.

---

### B-06 Write `src/core/artifacts.py` — Artifact Pydantic model

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

class Artifact(BaseModel):
    artifact_id: str                   # uuid4
    task_id: str
    pipeline_id: str | None = None
    kind: Literal["md","html","code","mermaid","pdf","zip","json","screenshot","csv"]
    filename: str
    content_path: str                  # relative to outputs/artifacts/{task_id}/
    mime_type: str
    size_bytes: int
    label_ar: str
    language: str | None = None        # for kind="code"
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Blocking check:** mypy clean (no type errors).

---

### B-07 Write `src/core/orchestrator.py`

**Must implement:**
- `is_compound_heuristic(message: str) -> bool` — cheap: regex + clause count
- `plan(message, locale) -> Pipeline` — calls LLM with `prompts/orchestrator.md`
- `run(pipeline, event_bus) -> AsyncGenerator` — sequential steps, fan-out (cap=5)
- `_resolve_params(params, results) -> dict` — JSONPath `$sN.field` resolution
- `_fan_out(step, items, cap=5) -> list[Task]` — concurrent sub-tasks

**`$askUser` handling:** emits `pipeline_paused` event with `required_fields[]` structure (see plan §10.5).

**Blocking check:** `tests/test_orchestrator.py` passes (plan parsing, param resolution, compound heuristic).

---

### B-08 Create `src/api/routes/__init__.py`

Empty package file. **Blocking check:** no import errors.

---

### B-09 Write `src/api/routes/intent.py`

```
POST /api/intent
Body:  { message: str }
Returns: { intent: str, confidence: float, missing_params: list[str], is_compound: bool }
```

**Rules:** RULE-26 (typed Pydantic models), RULE-27 (Arabic error messages on 4xx/5xx).

**Blocking check:** `curl -X POST localhost:8000/api/intent -d '{"message":"ابحث عن react"}'` returns `{ intent: "research" }`.

---

### B-10 Write `src/api/routes/chat.py`

```
POST /api/chat
Body:  { message: str, attachments?: list, force_skill?: str, approved_pipeline_id?: str }
Returns: { mode: "single"|"pipeline"|"need_params", task_id?: str, pipeline_id?: str, missing_params?: list }
```

**Routing logic:**
1. Rule-based intent detect (fast)
2. If confidence < 0.7 OR compound heuristic says maybe → LLM compound check
3. Simple → route to single skill, return `{ mode: "single", task_id }`
4. Compound → `orchestrator.plan()`, return `{ mode: "pipeline", pipeline_id }`

**Blocking check:** Simple goal → `mode: "single"` + `task_id`. Compound goal → `mode: "pipeline"` + `pipeline_id`.

---

### B-11 Write `src/api/routes/uploads.py`

```
POST /api/uploads  (multipart/form-data)
Returns: { attachment_id: str, url: str, mime: str, size: int }
```

Saves to `outputs/uploads/{uuid}/`. **Blocking check:** curl upload → response URL serves the file.

---

### B-12 Write `src/api/routes/artifacts.py`

```
GET  /api/artifacts/{id}           → Artifact metadata JSON
GET  /api/artifacts/{id}/preview   → inline content (HTML/MD/text)
GET  /api/artifacts/{id}/download  → file with Content-Disposition: attachment (ZIP support — G15)
POST /api/artifacts/{id}/regenerate → { artifact_id, status }
```

**Blocking check:** Round-trip: generate → download produces valid file.

---

### B-13 Write `src/api/routes/continuation.py`

```
GET /api/continuation/{task_or_pipeline_id}
Returns: { suggestions: [{ label_ar: str, prompt: str }] }
```

Async — uses `prompts/continuation.md` + task context, calls LLM. **2s timeout** — returns `{ suggestions: [] }` if too slow (G18).

**Blocking check:** Returns JSON within 3s for any task_id.

---

### B-14 Add pipeline + completion_prompt WS events to event bus

**Events to add** (see plan §10.5 for full shapes):
- `pipeline_plan`, `pipeline_approved`, `pipeline_step_start`, `pipeline_step_end`
- `pipeline_paused` (with `required_fields[]`), `pipeline_resumed`, `pipeline_end`
- `completion_prompt` (with `suggestions[]`)

**File:** wherever events are currently published (likely `src/core/event_bus.py`).

**Blocking check:** Server starts without errors; existing WS events still work.

---

### B-15 Wire all new routes into `src/api/main.py`

Include all routers from `src/api/routes/`. Also wire `/api/pipelines/{id}/approve`, `/api/pipelines/{id}/cancel`, `/api/pipelines/{id}/resume`, `GET /api/pipelines/{id}`.

**Blocking check:** All 11+ new endpoints return non-404.

---

### B-16 Write all backend tests

**Files:**
- `tests/test_orchestrator.py` — `is_compound_heuristic()`, plan parsing, `$sN.field` resolution
- `tests/test_prompt_loader.py` — `load_prompt()` locale injection, FileNotFoundError for missing files
- `tests/test_artifacts.py` — Artifact model validation

**Blocking check:** `pytest tests/` → 100% pass.

---

### B-17 Browser/API Verification

```bash
# Test intent endpoint
curl -X POST http://localhost:8000/api/intent \
  -H "Content-Type: application/json" \
  -d '{"message": "ابحث عن react frameworks"}'
# Expected: { "intent": "research", "confidence": ... }

# Test chat endpoint (simple)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "ابحث عن react"}'
# Expected: { "mode": "single", "task_id": "..." }

# Run all tests
pytest tests/
```

---

## Phase C — Core Chat Shell ⬜

> 23 tasks. Start after Phase B is verified.
> Tell Claude: **"ابدأ Phase C"**

Tasks in order:
- C-01 `lib/events.ts` — ALL WS event TypeScript types
- C-02 `lib/api.ts` — `apiFetch<T>()`, `apiPost<T>()`, typed endpoints
- C-03 `hooks/useTaskStream.ts` — reconnect + late-join + exponential backoff (plan §12)
- C-04 `lib/runtime-adapter.ts` — `useAgentRuntime()` bridging `useTaskStream` → assistant-ui
- C-05 `components/layout/AppShell.tsx`
- C-06 `components/layout/Sidebar.tsx` — task history, settings link, new-chat
- C-07 `components/layout/TopBar.tsx` — locale + theme toggles
- C-08 `components/layout/RightDrawer.tsx` — collapsible, only during execution
- C-09 `components/chat/EmptyState.tsx` — greeting + 6 quick-start chips
- C-10 `components/chat/MessageBubble.tsx` — user + assistant variants
- C-11 `components/chat/ChatThread.tsx` — AssistantRuntimeProvider wrapper
- C-12 `components/chat/Composer.tsx` — textarea + send + attachment + slash commands
- C-13 `hooks/useIntent.ts` — debounced 300ms `/api/intent`
- C-14 `components/chat/SkillBadge.tsx` — detected skill + 18-skill override dropdown
- C-15 `components/live/ActionIcon.tsx` — icon map (port from `app.js describeAction()`)
- C-16 `components/live/TimelineStrip.tsx` — accordion step list
- C-17 `components/live/LiveScreenshot.tsx` — screenshot in RightDrawer
- C-18 `components/skill-cards/AgentRunCard.tsx` — generic task card
- C-19 `components/chat/ContinuationCard.tsx` — completion + suggestions + [متابعة]/[إنهاء]
- C-20 Wire `ChatPage.tsx` composing all components
- C-21 `App.tsx` router: `/chat`, `/chat/settings`, `/chat/artifacts`
- C-22 `locales/ar.json` + `locales/en.json` (port all Arabic labels from legacy `index.html`)
- C-23 Browser verification per plan §15 Phase C checks

---

## Phase D — Existing Skill Cards (10) ⬜

> 11 tasks. Each card = 1 frontend component + update Python skill return value.

- D-01 `SearchResultCard` + update `search_agent.py`
- D-02 `ExploreReportCard` + update `explore.py` (MD artifact)
- D-03 `DesignTokensCard` + update `design_tokens.py` (Tailwind config artifact)
- D-04 `ComponentsGalleryCard` + update `find_components.py`
- D-05 `LoginCard` + update `login.py`
- D-06 `SignupCard` + update `signup.py`
- D-07 `TempSignupCard` + update `temp_signup.py`
- D-08 `CloneCard` + update `clone.py` (iframe preview + PDF artifact)
- D-09 `SiteCloneCard` + update `site_clone.py` (ZIP artifact)
- D-10 Refine `AgentRunCard` with all perception/decision/action event types
- D-11 Browser verification — each card in running/succeeded/failed states

**Each skill return value must include:** `summary_ar`, `summary_en`, `artifacts[]`, `final_message_ar`

---

## Phase E — Pipeline UI ⬜

> 7 tasks.

- E-01 `components/pipeline/PipelineStep.tsx` — step icon, status, expand, fan-out bar
- E-02 `components/pipeline/PipelineCard.tsx` — full pipeline plan
- E-03 `components/pipeline/PipelineApproval.tsx` — [▶ تشغيل] [✎ تعديل] [✕ إلغاء]
- E-04 `hooks/usePipeline.ts` — aggregates pipeline WS events + sub-task streams
- E-05 `pipeline_paused` → inline field form (required_fields[] per G06)
- E-06 Update `ChatPage.tsx` to handle `pipeline_id` response from `/api/chat`
- E-07 Browser E2E: compound Arabic goal → approval → execution → live updates

---

## Phase F — New Skills (8) ⬜

> 9 tasks. Backend skill + frontend card for each.

- F-01 `md_writer` — `ArtifactPanel` + `ArtifactActions` + `MarkdownArtifactCard`
- F-02 `html_artifact` — `HtmlSandbox` (CSP per plan §7) + `HtmlArtifactCard`
- F-03 `code_artifact` — `CodeBlock` (shiki) + `CodeArtifactCard`
- F-04 `mermaid_diagram` — mermaid.js SVG render + `MermaidArtifactCard`
- F-05 `pdf_export` — `@react-pdf/renderer` client-side + `PdfArtifactCard`
- F-06 `summarize` — `SummarizeCard` (Arabic bullets + word-count delta)
- F-07 `translate` — `TranslateCard` (side-by-side original + translation)
- F-08 `competitor_matrix` — sortable/filterable table + CSV export + `CompetitorMatrixCard`
- F-09 Browser verification per skill

---

## Phase G — Settings + Attachments ⬜

> 7 tasks.

- G-01 `ProvidersPanel.tsx` — port from `app.js` logic (8 providers, same API calls)
- G-02 `AccountsLedger.tsx` — port from `app.js`
- G-03 `ArchiveBrowser.tsx` — port from `app.js` (standalone in SettingsPage)
- G-04 `hooks/useArchiveSuggestion.ts` + `ArchiveSuggestionBanner.tsx` above Composer (G12)
- G-05 Composer drag-and-drop + paste file handler
- G-06 `POST /api/uploads` integration + `AttachmentPreview.tsx`
- G-07 Browser verification — drag/drop, settings, archive suggestion

---

## Phase H — Migration Cutover ⬜

> 11 tasks. **Irreversible from H-06 onward.**

- H-01 Full RTL audit (logical properties — no `mr-`/`ml-`/`text-left`/`text-right` without logic)
- H-02 Keyboard shortcuts: Enter=send, Shift+Enter=newline, Escape=close drawer, /=focus Composer
- H-03 All error states verified: network error, task failed, WS disconnect, artifact failure
- H-04 **Full Playwright E2E suite must pass 100%**
- H-05 `git commit "chore: pre-cutover checkpoint"`
- H-06 `src/api/main.py`: change `/` route → 301 redirect to `/chat`
- H-07 Delete `web/templates/index.html`
- H-08 Delete `web/static/app.js`
- H-09 Delete `web/static/styles.css`
- H-10 Update `README.md` with new `/chat` as primary URL
- H-11 Browser: `http://localhost:8000/` → redirects to `/chat`, all 18 skills work

---

## Phase I — Polish ⬜

> 8 tasks.

- I-01 Framer Motion: stagger animations + page transitions
- I-02 Dark mode full pass — all shadcn components
- I-03 Mobile: Sidebar → Sheet `<1024px`, RightDrawer → bottom Sheet `<768px`
- I-04 Code splitting: `React.lazy(() => import(...))` per skill card
- I-05 Performance: `useCallback`/`useMemo` for heavy renders (timeline, table sorts)
- I-06 Accessibility: `aria-label` on all icon buttons, keyboard navigation in pipeline steps
- I-07 Bundle size: main chunk target < 200KB gzip (`npm run build` + check)
- I-08 Final browser verification — all 18 skills, RTL, dark, mobile

---

## Key Architecture Reference

### Vite config (already written)

```typescript
// web-chat/vite.config.ts
base: '/chat/'
proxy: { '/api': 'http://localhost:8000', '/ws': { target: 'ws://localhost:8000', ws: true } }
build.outDir: '../web/static/chat'
```

### FastAPI mount (already written)

```python
# src/api/main.py
_CHAT_DIR = WEB_DIR / "static" / "chat"
if _CHAT_DIR.exists():
    app.mount("/chat", StaticFiles(directory=str(_CHAT_DIR), html=True), name="chat")
```

### Prompt template contract

Every `prompts/*.md` file must contain:
```
Respond to the user in {locale} (ISO 639-1 code). Do not switch languages mid-response.
```

Default locale is `"ar"`. User can switch to `"en"` in settings.

### Execution rules (applies to ALL tasks)

```
RULE-01  Never use `any` type — use `unknown` + type guards
RULE-02  Every component handles: loading, error, empty
RULE-03  Every REST call: try/catch + Arabic error in UI
RULE-07  Dark mode + RTL verified before marking task done
RULE-08  tsc --noEmit must pass after every task
RULE-21  One git commit per atomic task
RULE-22  Commit format: feat(phase-X): implement <component> — <description>
RULE-26  All FastAPI routes use typed Pydantic request/response models
RULE-27  All backend errors return Arabic { detail: str } on 4xx/5xx
```

---

## Continuing in a New Claude Session

Copy-paste this to start Claude where you left off:

```
أنا أعمل على مشروع WebSearchAi — استبدال واجهة الدردشة القديمة بـ React/Vite.
اقرأ ملف PROGRESS.md لترى الحالة الحالية.
Phase A اكتملت بالكامل.
ابدأ Phase B من المهمة B-01.
```

Or in English:
```
I'm working on WebSearchAi — replacing the old chat UI with React/Vite.
Read PROGRESS.md for current status.
Phase A is complete.
Start Phase B from task B-01.
```
