# Chat UI — Comprehensive Implementation Plan

> Status: **APPROVED v3 — HARDENED** — Gap analysis applied, execution contract added.
> Date: 2026-05-18 | Author: Claude (Opus 4.7)
> Target: Replace the legacy vanilla-JS tabbed UI with a unified professional React chat.

---

## Revision Log

| Version | Date | Change |
|---|---|---|
| v1 | 2026-05-18 | Initial proposal |
| v2 | 2026-05-18 | User clarifications: pipeline approval, fan-out, Node, language policy, new skills, UI/UX |
| **v3** | **2026-05-18** | **Hardened: 19 gaps fixed, execution contract + sequential task manifest added** |

---

## 0. Gap Analysis — Issues Found & Fixed in v3

> Every item below was a real risk of implementation failure or silent defect.

| # | Gap | Severity | Fix Applied |
|---|---|---|---|
| G01 | WeasyPrint requires GTK on Windows — uninstallable in most environments | BLOCKER | PDF moved to client-side `@react-pdf/renderer`; server export deferred to Phase I |
| G02 | `@ai-sdk/react` cannot connect to custom FastAPI WebSocket out-of-the-box | BLOCKER | Clarified: `@ai-sdk/react` dropped from MVP. `assistant-ui` uses a custom `LocalRuntime` adapter bridging `useTaskStream` |
| G03 | `react-router-dom` missing from tech stack | HIGH | Added to frontend deps in §3 |
| G04 | `assistant-ui` runtime adapter pattern not specified | HIGH | Exact adapter pattern added to §3.1 |
| G05 | WebSocket reconnect + late-connect recovery not specified | HIGH | `useTaskStream` reconnect contract added to §11 |
| G06 | `$askUser` event carries no field schema → frontend can't render input | HIGH | `required_fields[]` added to `pipeline_paused` event shape §9.5 |
| G07 | Intent detection and compound-task check both called on every keystroke — compound check is a slow LLM call | HIGH | Split: rule-based intent on debounced typing, LLM compound check on submit only §9.1 |
| G08 | `Artifact` Pydantic model never defined | HIGH | Full model added §4.1 |
| G09 | TypeScript `strict` mode not enforced | MEDIUM | Added to §3 + enforced in contract §16 |
| G10 | Font loading not specified — Tajawal missing at runtime | MEDIUM | `fontsource` packages added §3; link tags added to `index.html` spec §17-A3 |
| G11 | `HtmlSandbox` iframe sandbox attributes not specified — XSS risk | MEDIUM | `sandbox` + CSP attributes specified §7.2 |
| G12 | `ArchiveSuggestion` placed in SettingsPage — wrong location | MEDIUM | Moved to `useArchiveSuggestion` hook + banner above Composer §5 |
| G13 | HTTP client not specified — risk of inconsistent error handling | MEDIUM | Native `fetch` with typed wrappers in `lib/api.ts` specified §3 |
| G14 | `vite.config.ts` `base` path not set — assets 404 at `/chat/` prefix | MEDIUM | `base: '/chat/'` + proxy rules added §17-A2 |
| G15 | ZIP artifact endpoint missing for `site_clone` output | MEDIUM | `GET /api/artifacts/{id}/download` added §10 |
| G16 | Prompt migration: which existing files have inline prompts | MEDIUM | Full file list added §4.2 |
| G17 | Vitest + Playwright not in stack — no test framework for frontend | MEDIUM | Added to §3 |
| G18 | `completion_prompt` LLM call is synchronous and blocks UI — no timeout | LOW | Async pre-compute with 2s timeout; card shows without suggestions first §9.5 |
| G19 | No `Artifact` component routing: `artifacts.ts` MIME→component map not detailed | LOW | Full MIME map added §7 |

---

## 1. Goal

Build a single React/Vite chat page at `/chat` that:

1. Accepts free-form Arabic + English messages, RTL-first.
2. Auto-detects intent (rule-based, fast) with manual override + slash commands.
3. Streams 10+ agent WebSocket event types live.
4. Renders each skill's output in a spacious, professional Generative-UI template.
5. Handles multi-skill pipelines via the new orchestrator layer.
6. Supports file attachments + full message history.
7. Generates downloadable/previewable artifacts inline (.md, runnable HTML, code, Mermaid, PDF).
8. Presents a continuation card after every completion with LLM-suggested follow-ups.
9. Replaces the legacy UI completely — deleted in Phase H.

---

## 2. Architectural Decision Record (ADR)

| # | Decision | Why |
|---|---|---|
| ADR-1 | React/Vite SPA at `web-chat/`, built to `web/static/chat/`, served by FastAPI at `/chat` | No Node runtime in prod; single static artifact |
| ADR-2 | Hybrid intent: rule-based detect while typing + LLM compound-check on submit | Fast UX; slow LLM call only when actually needed |
| ADR-3 | `src/core/orchestrator.py` for multi-skill pipelines; approval gate ≥3 steps or credential steps | User-confirmed |
| ADR-4 | Legacy `/` hard-deleted in Phase H — no transitional period | User-confirmed |
| ADR-5 | Backend additions only — no rewrites to agent loop, task manager, event bus | Production risk |
| ADR-6 | `completion_prompt` WS event after every task/pipeline end → `ContinuationCard` UI | User-confirmed |
| ADR-7 | English LLM prompts in `prompts/` files; user-facing strings always Arabic | Model performance + maintainability |
| ADR-8 | Fan-out cap = 5 concurrent sub-tasks; rest queue | User-confirmed |
| ADR-9 | Client-side PDF via `@react-pdf/renderer` (no server system deps) | G01 fix: WeasyPrint fails on Windows |
| ADR-10 | `assistant-ui` with custom `LocalRuntime` adapter — NO Vercel AI SDK in MVP | G02 fix: AI SDK cannot bridge FastAPI WebSocket |

---

## 3. Tech Stack (v3 — corrected and complete)

### 3.1 Frontend (`web-chat/`)

```
Core
├── Vite 5.x                        build tool, base: '/chat/'
├── React 18.x                      UI framework
├── TypeScript 5.x (strict: true)   type safety — G09
├── react-router-dom 6.x            routing — G03

Chat shell
├── @assistant-ui/react             Thread, Composer, MessageList primitives
├── @assistant-ui/react-markdown    markdown message rendering
├── Custom LocalRuntime adapter     bridges useTaskStream → AssistantRuntimeProvider — G04

Design system
├── tailwindcss 3.x + @tailwindcss/typography
├── shadcn/ui (via CLI)             Button, Card, Dialog, Badge, Tabs, Tooltip, Popover
├── framer-motion 11.x              micro-animations
├── lucide-react                    icons

Content rendering
├── react-markdown + remark-gfm + rehype-katex  markdown + math
├── shiki                           syntax highlighting in CodeBlock
├── mermaid 11.x                    diagram rendering in MermaidArtifactCard
├── @react-pdf/renderer 3.x         client-side PDF generation — G01 fix

Fonts (self-hosted via fontsource — G10)
├── @fontsource/tajawal             Arabic UI font
├── @fontsource/inter               Latin UI font
├── @fontsource/jetbrains-mono      code font

State + data fetching
├── zustand 4.x                     global state (tasks, settings, artifacts)
├── @tanstack/react-query 5.x       REST cache (providers, accounts, archive)

Internationalization
├── i18next + react-i18next         AR/EN strings + locale switching
├── i18next-browser-languagedetector auto-detect browser locale

HTTP (G13 — native fetch only)
└── lib/api.ts                      typed fetch wrappers, no Axios dep

Testing (G17)
├── vitest + @testing-library/react unit + component tests
└── @playwright/test                E2E browser tests
```

### 3.2 Custom LocalRuntime Adapter (G04 — critical pattern)

```tsx
// web-chat/src/lib/runtime-adapter.ts
import { useLocalRuntime, LocalRuntimeOptions } from "@assistant-ui/react";
import { useTaskStream } from "../hooks/useTaskStream";

// Bridges FastAPI WebSocket task events → assistant-ui message model
export function useAgentRuntime(taskId: string | null): ReturnType<typeof useLocalRuntime> {
  const taskState = useTaskStream(taskId);
  const options: LocalRuntimeOptions = {
    initialMessages: [],
    // assistant-ui calls onNew when user sends a message
    // we intercept here and POST to /api/chat instead
    async onNew(message) { /* POST /api/chat, return task_id */ },
  };
  return useLocalRuntime(options);
}
```

### 3.3 Backend additions

```
src/core/orchestrator.py          NEW — skill-pipeline planner & executor
src/skills/artifact/              NEW package
  ├── __init__.py
  ├── md_writer.py
  ├── html_artifact.py
  ├── code_artifact.py
  ├── mermaid_diagram.py
  └── pdf_export.py               uses @react-pdf/renderer client-side; backend saves MD only
src/skills/utility/               NEW package
  ├── __init__.py
  ├── summarize.py
  └── translate.py
src/skills/competitor_matrix.py   NEW
src/api/routes/                   NEW package (extracted from main.py)
  ├── __init__.py
  ├── chat.py
  ├── intent.py
  ├── uploads.py
  ├── artifacts.py
  └── continuation.py
prompts/                          NEW — all LLM prompts as English MD files
  ├── planner.md
  ├── decider.md
  ├── critic.md
  ├── verifier.md
  ├── synthesizer.md
  ├── orchestrator.md
  ├── continuation.md
  ├── intent_classifier.md
  └── skills/
      ├── md_writer.md, html_artifact.md, code_artifact.md
      ├── summarize.md, translate.md, competitor_matrix.md
      └── explore.md, find_components.md, design_tokens.md
```

---

## 4. Language Policy (English prompts → Arabic responses)

### 4.1 Artifact Pydantic model (G08 — was missing)

```python
# src/core/artifacts.py  (NEW)
from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class Artifact(BaseModel):
    artifact_id: str                   # uuid4
    task_id: str
    pipeline_id: str | None = None
    kind: Literal[
        "md", "html", "code", "mermaid",
        "pdf", "zip", "json", "screenshot", "csv"
    ]
    filename: str                      # e.g. "report.md", "landing.html"
    content_path: str                  # relative to outputs/artifacts/{task_id}/
    mime_type: str
    size_bytes: int
    label_ar: str                      # Arabic display label shown in card footer
    language: str | None = None        # for kind="code" — "python", "ts", etc.
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Every skill's return value is extended with:
```python
{
  ...skill_specific_fields,
  "summary_ar": str,            # concise Arabic summary for chat bubble
  "summary_en": str | None,     # optional mirror
  "ar_locale_used": bool,
  "artifacts": list[Artifact],  # 0–N per skill
  "final_message_ar": str,      # explicit closing sentence shown in ContinuationCard
}
```

### 4.2 Prompt migration map (G16 — existing inline prompts to extract)

| Current file | Prompt content to extract | → Target file |
|---|---|---|
| `src/core/planner.py` | `SYSTEM_PROMPT`, goal→plan template | `prompts/planner.md` |
| `src/core/agent.py` | decider system prompt + action schema | `prompts/decider.md` |
| `src/core/critic.py` | content judgment prompt | `prompts/critic.md` |
| `src/core/perception.py` | snapshot prompt | part of `prompts/decider.md` |
| `src/core/search_agent.py` | synthesis prompt, ranking prompt | `prompts/synthesizer.md` |
| `src/core/verifier.py` | verification prompt | `prompts/verifier.md` |
| `src/skills/explore.py` | site analysis prompt → JSON report | `prompts/skills/explore.md` |
| `src/skills/find_components.py` | JSX conversion prompt | `prompts/skills/find_components.md` |
| `src/skills/design_tokens.py` | Arabic MD report prompt | `prompts/skills/design_tokens.md` |
| `src/skills/clone.py` | Tailwind rebuild prompt | `prompts/skills/clone.md` |

**`load_prompt(name, locale)` helper:**
```python
# src/core/prompt_loader.py  (NEW)
from pathlib import Path
_BASE = Path(__file__).parent.parent.parent / "prompts"

def load_prompt(name: str, locale: str = "ar", **kwargs) -> str:
    """Load an English prompt template and inject {locale} + any extra vars."""
    path = _BASE / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    return template.format(locale=locale, **kwargs)
```

### 4.3 Prompt template contract

Every prompt file must contain the line:
```
Respond to the user in {locale} (ISO 639-1 code). Do not switch languages mid-response.
```
Locale default is `"ar"` unless the user explicitly sets EN in settings.

---

## 5. Directory Structure (v3 complete)

```
web-chat/
├── package.json
├── vite.config.ts              base: '/chat/', proxy /api + /ws → :8000
├── tsconfig.json               strict: true, paths aliases
├── tailwind.config.ts
├── postcss.config.js
├── playwright.config.ts        E2E tests
├── index.html                  font preloads, dir="rtl" default
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx
    ├── App.tsx                 router setup
    ├── routes/
    │   ├── ChatPage.tsx
    │   ├── SettingsPage.tsx
    │   └── ArtifactsPage.tsx
    ├── components/
    │   ├── chat/
    │   │   ├── ChatThread.tsx
    │   │   ├── Composer.tsx            input + attachment + slash + archive banner
    │   │   ├── ArchiveSuggestionBanner.tsx  (G12 — was wrongly in SettingsPage)
    │   │   ├── SkillBadge.tsx
    │   │   ├── MessageBubble.tsx
    │   │   ├── AttachmentPreview.tsx
    │   │   ├── ContinuationCard.tsx
    │   │   └── EmptyState.tsx
    │   ├── skill-cards/
    │   │   ├── SearchResultCard.tsx
    │   │   ├── SignupCard.tsx
    │   │   ├── LoginCard.tsx
    │   │   ├── ExploreReportCard.tsx
    │   │   ├── CloneCard.tsx
    │   │   ├── SiteCloneCard.tsx
    │   │   ├── ComponentsGalleryCard.tsx
    │   │   ├── DesignTokensCard.tsx
    │   │   ├── TempSignupCard.tsx
    │   │   ├── AgentRunCard.tsx
    │   │   ├── CompetitorMatrixCard.tsx
    │   │   ├── MarkdownArtifactCard.tsx
    │   │   ├── HtmlArtifactCard.tsx
    │   │   ├── CodeArtifactCard.tsx
    │   │   ├── MermaidArtifactCard.tsx
    │   │   ├── PdfArtifactCard.tsx
    │   │   ├── SummarizeCard.tsx
    │   │   └── TranslateCard.tsx
    │   ├── artifact/
    │   │   ├── ArtifactPanel.tsx       universal wrapper: header + actions
    │   │   ├── ArtifactActions.tsx     download / copy / fullscreen / regenerate
    │   │   ├── HtmlSandbox.tsx         sandboxed iframe (G11 — CSP specified)
    │   │   ├── CodeBlock.tsx           shiki-rendered
    │   │   └── MarkdownPreview.tsx
    │   ├── pipeline/
    │   │   ├── PipelineCard.tsx
    │   │   ├── PipelineStep.tsx
    │   │   └── PipelineApproval.tsx
    │   ├── live/
    │   │   ├── LiveScreenshot.tsx
    │   │   ├── TimelineStrip.tsx
    │   │   └── ActionIcon.tsx
    │   ├── settings/
    │   │   ├── ProvidersPanel.tsx
    │   │   ├── AccountsLedger.tsx
    │   │   └── ArchiveBrowser.tsx      (standalone browser — not archive suggestions)
    │   ├── layout/
    │   │   ├── AppShell.tsx
    │   │   ├── Sidebar.tsx
    │   │   ├── TopBar.tsx
    │   │   └── RightDrawer.tsx
    │   └── ui/                         shadcn primitives (auto-generated)
    ├── hooks/
    │   ├── useTaskStream.ts            WebSocket + reconnect + late-join (G05)
    │   ├── useIntent.ts                debounced rule-based detect (G07)
    │   ├── usePipeline.ts
    │   ├── useArchive.ts
    │   ├── useArchiveSuggestion.ts     (G12 — was missing)
    │   ├── useArtifact.ts
    │   └── useContinuation.ts
    ├── lib/
    │   ├── api.ts                      fetch wrappers (G13), typed endpoints
    │   ├── events.ts                   all WS event type definitions
    │   ├── runtime-adapter.ts          assistant-ui LocalRuntime (G04)
    │   ├── skills.ts                   skill metadata
    │   ├── artifacts.ts                MIME → component map (G19)
    │   └── slash-commands.ts
    ├── stores/
    │   ├── tasksStore.ts
    │   ├── settingsStore.ts            locale, theme, headless, vision, provider
    │   └── artifactsStore.ts
    ├── locales/
    │   ├── ar.json
    │   └── en.json
    └── styles/globals.css

src/ (backend additions)
├── core/
│   ├── orchestrator.py
│   ├── artifacts.py               Artifact model
│   └── prompt_loader.py
├── skills/artifact/
│   ├── __init__.py, md_writer.py, html_artifact.py
│   ├── code_artifact.py, mermaid_diagram.py, pdf_export.py
├── skills/utility/
│   ├── __init__.py, summarize.py, translate.py
└── skills/competitor_matrix.py

prompts/ (at project root)
├── planner.md, decider.md, critic.md, verifier.md, synthesizer.md
├── orchestrator.md, continuation.md, intent_classifier.md
└── skills/*.md
```

---

## 6. Artifact MIME Map (G19)

```ts
// lib/artifacts.ts
export const ARTIFACT_CARD_MAP: Record<Artifact["kind"], ComponentType<ArtifactCardProps>> = {
  md:         MarkdownArtifactCard,
  html:       HtmlArtifactCard,
  code:       CodeArtifactCard,
  mermaid:    MermaidArtifactCard,
  pdf:        PdfArtifactCard,
  zip:        ZipArtifactCard,      // download-only, no preview
  json:       CodeArtifactCard,     // language="json"
  screenshot: ImageArtifactCard,    // <img> wrapped in ArtifactPanel
  csv:        CsvArtifactCard,      // table preview + download
};
```

---

## 7. HtmlSandbox — Security Spec (G11)

```tsx
// components/artifact/HtmlSandbox.tsx
<iframe
  srcDoc={html}
  sandbox="allow-scripts allow-same-origin"
  // NO allow-forms, allow-top-navigation, allow-popups
  // Content-Security-Policy via <meta> injected into srcDoc:
  // "default-src 'self' 'unsafe-inline' 'unsafe-eval'
  //  https://cdn.tailwindcss.com https://fonts.googleapis.com;"
  referrerPolicy="no-referrer"
  title="html-artifact-preview"
  className="w-full border-0 rounded-b-2xl"
  style={{ height: iframeHeight, resize: "vertical", overflow: "auto" }}
/>
```

The `html_artifact.py` backend injects a `<meta>` CSP tag and a Tailwind CDN `<script>` automatically so every generated page is self-contained and styled.

---

## 8. Legacy UI: Keep vs Port vs Delete

### KEEP (untouched — consumed via existing APIs)
- All 40+ REST endpoints in `src/api/main.py`
- `/ws/{task_id}` WebSocket + all existing event types
- `src/core/intent_router.py`, `planner.py`, `agent.py`, `critic.py`
- All existing `src/skills/*.py` — internals unchanged, return contract extended
- `src/api/tasks.py`

### PORT (logic carried into React, source file deleted after Phase H)
| Legacy source | New home |
|---|---|
| `app.js describeAction()` | `lib/events.ts` + `components/live/ActionIcon.tsx` |
| `app.js handleEvent()` | `hooks/useTaskStream.ts` |
| `app.js collectSources()` | `components/skill-cards/SearchResultCard.tsx` |
| `app.js buildHeroFromObject()` + report rendering | `components/skill-cards/*Card.tsx` |
| `app.js loadProviders/testProvider` | `components/settings/ProvidersPanel.tsx` |
| `app.js loadAccounts` | `components/settings/AccountsLedger.tsx` |
| `app.js loadArchive/searchArchive` | `components/settings/ArchiveBrowser.tsx` |
| `app.js checkArchiveSuggestion` | `hooks/useArchiveSuggestion.ts` + `ArchiveSuggestionBanner.tsx` |
| Arabic labels from `index.html` | `locales/ar.json` |

### DELETE in Phase H (hard delete, no backup)
- `web/templates/index.html`
- `web/static/app.js`
- `web/static/styles.css`
- FastAPI `/` route → 301 redirect to `/chat`

---

## 9. Complete Skill → Card Map (18 skills)

### 9.1 Existing (10)

| Skill | Intent triggers | Card | Required inputs | Live events | Final render |
|---|---|---|---|---|---|
| `research` | "ابحث عن…" + fallback | `SearchResultCard` | goal | research_round, candidate_selected, content_critiqued, synthesis_done | numbered results + cited synthesis + MD artifact |
| `signup` | "اشترك في…", "sign up" | `SignupCard` | site_url, full_name? | perception, decision | credentials card + verification badge |
| `temp_signup` | "أنشئ حساب مؤقت" | `TempSignupCard` | site_url, profile_name | + session persistence | account card + ledger link |
| `login` | "سجّل دخول…" | `LoginCard` | site_url, email, password | perception, decision | success/fail + screenshot |
| `explore` | "حلّل…", "analyze…" | `ExploreReportCard` | site_url, depth_hint | agent steps | 5-tab report + MD artifact download |
| `clone` | "انسخ هذه الصفحة" | `CloneCard` | url, max_assets | perception | iframe preview + download + PDF artifact |
| `site_clone` | "انسخ الموقع كامل" | `SiteCloneCard` | url, max_pages | per-page progress | page tree + ZIP artifact |
| `components` | "ابحث عن مكوّنات" | `ComponentsGalleryCard` | query, max_pages | research events | gallery grid, each variant in HtmlArtifactCard |
| `design_tokens` | "استخرج الألوان" | `DesignTokensCard` | url | perception | swatches + fonts + Tailwind config CodeArtifact |
| `run` / generic | anything with URL | `AgentRunCard` | goal | perception, decision, action_result, verdict | live screenshot + timeline |

### 9.2 New artifact skills (5)

| Skill | Intent triggers | Card | Output | Artifact kind |
|---|---|---|---|---|
| `md_writer` | "اكتب تقرير ماركداون", "make .md file" | `MarkdownArtifactCard` | KaTeX + GFM rendered + download | `md` |
| `html_artifact` | "اعمل صفحة HTML", "create landing page" | `HtmlArtifactCard` | live iframe + resize + open in tab | `html` |
| `code_artifact` | "اكتب كود بايثون", "generate code" | `CodeArtifactCard` | shiki highlighted + copy + download | `code` |
| `mermaid_diagram` | "ارسم مخطط…", "diagram of…" | `MermaidArtifactCard` | SVG rendered + download SVG/PNG | `mermaid` |
| `pdf_export` | "صدّر PDF", "export as PDF" | `PdfArtifactCard` | client-side render via `@react-pdf/renderer` | `pdf` |

### 9.3 New utility skills (2)

| Skill | Intent triggers | Card | Output |
|---|---|---|---|
| `summarize` | "لخّص لي…" | `SummarizeCard` | Arabic summary + bullets + word-count delta |
| `translate` | "ترجم…" | `TranslateCard` | side-by-side original + translation |

### 9.4 New pipeline-native skill (1)

| Skill | Intent triggers | Card | Pipeline | Output |
|---|---|---|---|---|
| `competitor_matrix` | "قارن منافسين…" | `CompetitorMatrixCard` | research → explore×5 → summarize | Interactive table (rows=sites, cols=features/tech/pricing) + CSV artifact |

---

## 10. Pipeline Orchestrator — Full Spec

### 10.1 Routing logic (G07 fix — split into 2 stages)

```python
# Stage 1: runs in /api/chat BEFORE returning (fast, < 50ms)
intent = intent_router.detect(message)     # pure pattern matching

# Stage 2: runs only at SUBMIT time (may call LLM, up to 2s)
if intent.confidence >= 0.7:
    compound = is_compound_heuristic(message)   # cheap: regex + clause count
    if compound == "maybe":
        compound = await is_compound_llm(message)  # LLM classifier call
else:
    compound = True   # low confidence = probably multi-skill

if not compound:
    → single skill execution (existing /api/{skill} path)
else:
    → orchestrator.plan(message)
```

`useIntent` hook calls `/api/intent` (rule-based only, no compound check) debounced 300ms while user types — this is FAST. Compound detection only happens on submit.

### 10.2 Pipeline data model

```python
@dataclass
class Pipeline:
    pipeline_id: str
    goal: str
    steps: list[PipelineStep]
    status: Literal["planning", "awaiting_approval", "running", "done", "failed"]
    fan_out_cap: int = 5
    locale: str = "ar"

@dataclass
class PipelineStep:
    step_id: str
    skill: str
    params: dict                  # may contain "$sN.field" refs
    fan_out: bool = False
    fan_out_source: str | None    # "$s1.results[*]"
    depends_on: list[str] = field(default_factory=list)
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    sub_tasks: list[str] = field(default_factory=list)
    result: Any = None
```

### 10.3 Example pipeline

```yaml
goal: "ابحث عن منافسين عقارات لديهم مواقع، حلّل مميزاتهم، سجّل دخول، واستكشف الصفحات الداخلية"
steps:
  - id: s1   skill: research      params: { goal: "real estate competitor websites Riyadh" }
  - id: s2   skill: explore       fan_out: true   fan_out_source: "$s1.results[*]"
             params: { site_url: "$item.url", depth_hint: "thorough" }   depends_on: [s1]
  - id: s3   skill: login         fan_out: true   fan_out_source: "$s2.results[*]"
             params: { site_url: "$item.site", email: "$askUser", password: "$askUser" }
             depends_on: [s2]
  - id: s4   skill: site_clone    fan_out: true   fan_out_source: "$s2.results[*]"
             params: { url: "$item.site", max_pages: 50 }   depends_on: [s2]
  - id: s5   skill: competitor_matrix   params: { from_explore: "$s2.results" }   depends_on: [s2]
```

### 10.4 Execution rules

- Sequential by default; fan-out only when `fan_out: true`
- Fan-out cap = 5 concurrent; rest queue (FIFO)
- Approval gate: fires if `len(steps) >= 3 OR any skill in [login, signup, temp_signup]`
- Failure policy: pause pipeline → emit `pipeline_paused` → user picks (retry/skip/abort)
- Output piping: JSONPath `$sN.field` resolved before step starts

### 10.5 WebSocket events (v3 — corrected, G06 fix for `pipeline_paused`)

```
pipeline_plan        { pipeline_id, goal, steps[], fan_out_cap }
pipeline_approved    { pipeline_id }
pipeline_step_start  { pipeline_id, step_id, skill, task_id, fan_out_index? }
pipeline_step_end    { pipeline_id, step_id, status, result, artifacts[] }
pipeline_paused      {                                        ← G06 fix
  pipeline_id, step_id, reason,
  required_fields: [                                         ← frontend renders this
    { name: str, type: "text"|"email"|"password"|"url"|"number",
      label_ar: str, required: bool }
  ]
}
pipeline_resumed     { pipeline_id, step_id }
pipeline_end         { pipeline_id, status, summary_ar, artifacts[] }
completion_prompt    { task_id?, pipeline_id?, suggestions: [{ label_ar, prompt }] }
                     ← suggestions may arrive up to 2s after task_end (pre-computed async)
```

---

## 11. New REST Endpoints (v3 — complete with G15 fix)

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/intent` | `{ message }` | `{ intent, confidence, missing_params[], is_compound }` |
| POST | `/api/chat` | `{ message, attachments?, force_skill?, approved_pipeline_id? }` | `{ mode, task_id?, pipeline_id?, missing_params? }` |
| POST | `/api/pipelines/{id}/approve` | `{ edits? }` | `{ ok }` |
| POST | `/api/pipelines/{id}/cancel` | — | `{ ok }` |
| POST | `/api/pipelines/{id}/resume` | `{ user_input: { field: value } }` | `{ ok }` |
| GET | `/api/pipelines/{id}` | — | full pipeline state |
| POST | `/api/uploads` | multipart/form-data | `{ attachment_id, url, mime, size }` |
| GET | `/api/artifacts/{id}` | — | `Artifact` metadata JSON |
| GET | `/api/artifacts/{id}/preview` | — | inline content (HTML/MD/text) |
| GET | `/api/artifacts/{id}/download` | — | file download with Content-Disposition (G15 — ZIP support) |
| POST | `/api/artifacts/{id}/regenerate` | `{ tweaks? }` | `{ artifact_id, status }` |
| GET | `/api/continuation/{task_or_pipeline_id}` | — | `{ suggestions: [{ label_ar, prompt }] }` |

---

## 12. WebSocket — `useTaskStream` Contract (G05 fix)

```ts
// hooks/useTaskStream.ts — full reconnect + late-join recovery

type TaskState = {
  status: "idle" | "running" | "succeeded" | "failed" | "cancelled";
  plan?: Plan;
  steps: TimelineStep[];
  screenshot?: string;
  verdict?: Verdict;
  result?: TaskResult;
  sources: Source[];
  researchRounds: ResearchRound[];
  artifacts: Artifact[];
  continuationSuggestions?: ContinuationSuggestion[];
};

// Lifecycle:
// 1. On mount with task_id:
//    a. FIRST: fetch GET /api/tasks/{task_id}/events → replay all past events to build state
//    b. If task already succeeded/failed: skip WS, mark done
//    c. Else: open WS /ws/{task_id} and handle new events
// 2. On WS disconnect:
//    - Retry with exponential backoff: 1s, 2s, 4s, 8s, 16s (5 attempts max)
//    - After 5 failures: set error state, show "انقطع الاتصال — [إعادة المحاولة]" banner
// 3. On task_end or status=succeeded/failed/cancelled: close WS, mark done permanently
// 4. On unmount: close WS immediately
```

---

## 13. UI/UX Design System

### 13.1 Layout
- **AppShell**: collapsible Sidebar (240px) + centered Chat column (max-w-[820px]) + collapsible RightDrawer (360px — opens ONLY during execution)
- Generous whitespace: `py-8` between cards, `px-6` inside cards, `gap-6` in grids
- Single primary action per surface — no button clusters

### 13.2 Typography
- Arabic: `@fontsource/tajawal` (300, 400, 500, 700 weights)
- Latin: `@fontsource/inter`
- Code: `@fontsource/jetbrains-mono`
- Sizes: `text-base` chat, `text-lg` card headings, `text-sm` metadata, `text-xs` timestamps

### 13.3 Color
- Light default (`bg-white`, `text-slate-900`) + Dark toggle in TopBar
- Accent: `indigo-600` — applied only to icons, badges, primary buttons
- Status: `emerald` (success), `amber` (running), `rose` (failed), `slate` (pending)
- Skill badge palette (each skill has a distinct hue, curated 18-color set, no neon)

### 13.4 Skill card anatomy (universal template)
```
╔══════════════════════════════════════════════════════╗
║  [Skill Icon]  Skill Name            [badge]  [···] ║  header — bg-white, border-b
╠══════════════════════════════════════════════════════╣
║                                                      ║
║   content area — px-6 py-5 — no bg tint             ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║  [📎 artifact N]  [📥 download]   [⏱ 4.2s]  [↻]   ║  footer — text-sm text-slate-500
╚══════════════════════════════════════════════════════╝
rounded-2xl  shadow-sm  border border-slate-100
entry: framer-motion opacity 0→1, y 8→0, duration 200ms
```

### 13.5 Pipeline card
```
╔══════════════════════════════════════════════════════╗
║  🧠  خطة من 4 خطوات          [▶ تشغيل]  [✎ تعديل]  ║
╠══════════════════════════════════════════════════════╣
║  ① 🔍 بحث المنافسين                     ● pending  ║
║     يبحث عن مواقع عقارية في الرياض               ║
║                                                      ║
║  ② 🎨 استكشاف (متوازي ×5)              ● pending  ║
║  ③ 📧 تسجيل دخول  ⚠ يحتاج بيانات        ● pending  ║
║  ④ 🗺 أرشفة الصفحات (متوازي ×5)        ● pending  ║
╚══════════════════════════════════════════════════════╝
```
- Fan-out steps: `×N` chip + progress bar (e.g. `████░░ 3/5`)
- Failed: rose highlight + `[↻ إعادة]` `[⏭ تخطي]` `[✕ إلغاء]`

### 13.6 Continuation card
```
╔══════════════════════════════════════════════════════╗
║  ✅  اكتملت المهمة بنجاح                             ║
║                                                      ║
║  هل توجد مهمة أخرى؟                                 ║
║  · صدّر التقرير PDF          → one-click            ║
║  · حلل موقع منافس آخر        → one-click            ║
║  · لخّص النتائج في 5 نقاط    → one-click            ║
║                                                      ║
║  [متابعة ↩]                         [إنهاء ✕]       ║
╚══════════════════════════════════════════════════════╝
```
- Shows immediately after task_end (without suggestions)
- Suggestions append ≤2s later via `completion_prompt` event
- `[متابعة]`: keeps thread context, focuses Composer
- `[إنهاء]`: collapses thread, new messages start fresh context
- Suggestion chips are one-click → pre-fills Composer + submits

### 13.7 Empty state
```
╔══════════════════════════════════════════════════════╗
║  👋  مرحباً، كيف يمكنني مساعدتك؟                    ║
║                                                      ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐           ║
║  │🔍 ابحث    │  │🎨 حلّل   │  │📄 تقرير MD│           ║
║  │عن منافسين│  │موقع      │  │           │           ║
║  └──────────┘  └──────────┘  └──────────┘           ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐           ║
║  │🌐 صفحة   │  │📊 مقارنة │  │🔐 حساب   │           ║
║  │HTML      │  │تنافسية   │  │جديد      │           ║
║  └──────────┘  └──────────┘  └──────────┘           ║
╚══════════════════════════════════════════════════════╝
```

---

## 14. Implementation Phases (v3 — 9 phases, each with DoD)

### Phase A — Scaffolding

**Tasks:**
1. `mkdir web-chat && cd web-chat && npm create vite@latest . -- --template react-ts`
2. Install all deps from §3.1 in one `npm install` command
3. Configure `vite.config.ts` with `base: '/chat/'`, proxy `/api → :8000`, proxy `/ws → ws://localhost:8000`
4. Configure `tsconfig.json` with `"strict": true` + path aliases (`@/` → `src/`)
5. Set up `tailwind.config.ts` with `fontFamily: { arabic: ['Tajawal'], sans: ['Inter'] }`
6. Add shadcn/ui via CLI: `npx shadcn-ui@latest init`
7. Write `index.html` with `<html dir="rtl" lang="ar">`, Tajawal/Inter preload links
8. Add `/chat` mount in `src/api/main.py` (`StaticFiles` + `index.html` fallback)
9. Add placeholder `src/routes/ChatPage.tsx` with "جاري البناء"
10. Run `npm run dev` and verify proxy works: `GET /chat` shows the app, `GET /api/tasks` proxied correctly

**DoD:**
- `http://localhost:5173/chat` renders correctly (React app, RTL)
- `http://localhost:8000/chat` renders the built app (after `npm run build`)
- No TypeScript errors (`npm run tsc -- --noEmit`)
- No console errors
- Tailwind classes applied, Arabic font loaded

---

### Phase B — Prompt extraction + backend additions

**Tasks:**
1. Create `prompts/` directory at project root
2. Extract each inline prompt per §4.2 migration map → corresponding `.md` file in English
3. Write `src/core/prompt_loader.py` with `load_prompt(name, locale)` helper
4. Update `planner.py`, `agent.py`, `critic.py`, `perception.py`, `search_agent.py`, `verifier.py`, `explore.py`, `find_components.py`, `design_tokens.py`, `clone.py` to use `load_prompt()` instead of inline strings
5. Create `src/core/artifacts.py` with `Artifact` Pydantic model
6. Write `src/core/orchestrator.py` with `plan()`, `run()`, `_resolve_params()`, `_fan_out()`
7. Create `src/api/routes/__init__.py` package
8. Write `src/api/routes/intent.py` — POST `/api/intent`
9. Write `src/api/routes/chat.py` — POST `/api/chat` (intent→route→stream)
10. Write `src/api/routes/uploads.py` — POST `/api/uploads`
11. Write `src/api/routes/artifacts.py` — GET/POST artifact endpoints + ZIP download (G15)
12. Write `src/api/routes/continuation.py` — GET `/api/continuation/{id}`
13. Add new WS event types to event bus (`pipeline_*`, `completion_prompt`)
14. Wire all new routes into `src/api/main.py`
15. Write `tests/test_orchestrator.py` — test `is_compound_heuristic()`, plan parsing, `$sN.field` resolution
16. Write `tests/test_prompt_loader.py` — test `load_prompt()` with locale injection
17. Run `pytest tests/` — must pass 100%

**DoD:**
- `POST http://localhost:8000/api/intent` returns `{ intent, confidence }` for sample messages
- `POST http://localhost:8000/api/chat` returns `{ mode: "single", task_id }` for a simple goal
- All existing tests still pass
- No import errors on server startup

---

### Phase C — Core chat shell

**Tasks:**
1. Write `lib/events.ts` — TypeScript types for ALL WS events (copy from `app.js handleEvent` mapping)
2. Write `lib/api.ts` — typed `apiFetch<T>()` wrapper, `apiPost<T>()`, WS factory
3. Write `hooks/useTaskStream.ts` — full reconnect + late-join recovery per §12
4. Write `lib/runtime-adapter.ts` — `useAgentRuntime()` bridging `useTaskStream` → `assistant-ui`
5. Write `components/layout/AppShell.tsx` — Sidebar + main + RightDrawer layout
6. Write `components/layout/Sidebar.tsx` — task history list, settings link, new-chat button
7. Write `components/layout/TopBar.tsx` — locale toggle, theme toggle, settings icon
8. Write `components/layout/RightDrawer.tsx` — collapsible, only visible during task execution
9. Write `components/chat/EmptyState.tsx` — greeting + 6 quick-start chips
10. Write `components/chat/ChatThread.tsx` — `AssistantRuntimeProvider` wrapping the thread
11. Write `components/chat/MessageBubble.tsx` — user + assistant message renders
12. Write `components/chat/Composer.tsx` — textarea, send, attachment icon, slash command detection
13. Write `hooks/useIntent.ts` — debounced 300ms call to `/api/intent`
14. Write `components/chat/SkillBadge.tsx` — detected skill badge + 18-item override dropdown
15. Write `components/live/ActionIcon.tsx` — icon map from legacy `describeAction()`
16. Write `components/live/TimelineStrip.tsx` — accordion list of steps
17. Write `components/live/LiveScreenshot.tsx` — screenshot in RightDrawer
18. Write `components/skill-cards/AgentRunCard.tsx` — generic card wiring `useTaskStream` → live UI
19. Write `components/chat/ContinuationCard.tsx` — completion + suggestions + buttons
20. Wire `ChatPage.tsx` composing all of the above
21. Configure `react-router-dom` in `App.tsx` with `/chat`, `/chat/settings`, `/chat/artifacts`

**DoD — browser tests:**
- Send a goal → `AgentRunCard` appears with live screenshot in drawer
- Timeline expands and shows steps
- `SkillBadge` shows detected skill, dropdown overrides it
- Typing `/search` in Composer forces search skill
- `ContinuationCard` appears after task completes
- RTL renders correctly (text right-aligned, flex reversed)
- Dark mode toggle works for all components above
- Mobile `<1024px`: Sidebar collapses to sheet
- No TypeScript errors

---

### Phase D — Existing skill cards (10)

**For EACH card, tasks follow this template:**
1. Write `components/skill-cards/<Name>Card.tsx`
2. Update corresponding `src/skills/<name>.py` return value to include `summary_ar`, `artifacts[]`, `final_message_ar`
3. Browser test: run the actual skill via chat → verify card renders correctly with live data

**Priority order:**
1. `SearchResultCard` — most common skill
2. `ExploreReportCard` + `src/skills/explore.py` update (MD artifact)
3. `DesignTokensCard` + Tailwind config CodeArtifact
4. `ComponentsGalleryCard` — verify viewer.html iframe renders
5. `LoginCard`
6. `SignupCard`
7. `TempSignupCard`
8. `CloneCard` + iframe preview
9. `SiteCloneCard` + ZIP artifact
10. `AgentRunCard` refinement (generic fallback, now with all events)

**DoD per card:**
- Real skill execution triggered via chat input
- Card renders in all 3 states: running (live events), succeeded, failed
- Download/copy actions work
- Arabic text correct throughout
- Dark mode works

---

### Phase E — Pipeline UI

**Tasks:**
1. Write `components/pipeline/PipelineStep.tsx` — single step: icon, status, expand, fan-out bar
2. Write `components/pipeline/PipelineCard.tsx` — pipeline plan with all steps
3. Write `components/pipeline/PipelineApproval.tsx` — [▶ تشغيل] [✎ تعديل] [✕ إلغاء]
4. Write `hooks/usePipeline.ts` — aggregates pipeline WS events + each sub-task's `useTaskStream`
5. Handle `pipeline_paused` event → inline field form (G06) rendered inside active step
6. Update `ChatPage.tsx` to detect `pipeline_id` in `/api/chat` response and render `PipelineCard`
7. Test the full compound-task flow end-to-end in browser

**DoD:**
- Type a compound goal in Arabic → pipeline plan appears
- Approval card shows before execution
- Each step updates live (pending → running → done)
- Fan-out steps show `×N` chip + progress bar
- `pipeline_paused` renders the `required_fields` form inline
- Resume after input continues execution
- Failed step shows retry/skip/abort options

---

### Phase F — New skills (artifact + utility + competitor_matrix)

**For each skill, tasks:**
1. Backend: write `src/skills/artifact/<name>.py` (or utility)
2. Add route in `src/api/routes/chat.py` for the new intent kind
3. Frontend: write `components/artifact/<framework>` (if first use of that renderer)
4. Frontend: write `components/skill-cards/<Name>Card.tsx`
5. Browser test with real input

**Order:**
1. `md_writer` + `MarkdownArtifactCard` + shared `ArtifactPanel` + `ArtifactActions`
2. `html_artifact` + `HtmlArtifactCard` + `HtmlSandbox` (sandbox attributes per §7)
3. `code_artifact` + `CodeArtifactCard` + `CodeBlock` (shiki)
4. `mermaid_diagram` + `MermaidArtifactCard` (mermaid.js render)
5. `pdf_export` + `PdfArtifactCard` (`@react-pdf/renderer` client-side)
6. `summarize` + `SummarizeCard`
7. `translate` + `TranslateCard`
8. `competitor_matrix` + `CompetitorMatrixCard` (sortable/filterable table + CSV export)

**DoD per skill:**
- Actual LLM output generates the artifact (not hardcoded fixture)
- Download button produces a valid downloadable file
- HTML artifacts render in sandboxed iframe (no CSP violations in console)
- Mermaid diagrams render SVG correctly
- PDF renders Arabic text (test with Arabic content)
- All actions (copy, download, fullscreen, regenerate) function correctly

---

### Phase G — Settings migration + attachments

**Tasks:**
1. Port `ProvidersPanel.tsx` from `app.js` logic — same 8 providers, same API calls
2. Port `AccountsLedger.tsx`
3. Port `ArchiveBrowser.tsx` (standalone browser in SettingsPage)
4. Write `hooks/useArchiveSuggestion.ts` + `ArchiveSuggestionBanner.tsx` in Composer (G12)
5. Composer: add drag-and-drop + paste file handler
6. `POST /api/uploads` integration
7. Write `AttachmentPreview.tsx` (images inline, PDF icon, generic file chip)
8. Pass `attachments[]` array through `/api/chat` request

**DoD:**
- Provider cards load, test button returns latency
- Accounts ledger shows all profiles
- Archive search works
- Archive suggestion banner appears for repeated goals (threshold 0.45)
- Drag-and-drop an image → appears as preview above Composer
- Pasted image: same
- Attachment sent with message, shown in chat thread

---

### Phase H — Migration cutover

**Tasks (in order — irreversible from step 3 onward):**
1. Full RTL audit: every component in RTL mode, fix any `mr-`/`ml-`/`text-left`/`text-right` not using logical properties
2. Keyboard shortcuts: `Enter` to send, `Shift+Enter` newline, `Escape` to close drawer, `/` to focus Composer
3. All error states verified: network error, task failed, WS disconnect, artifact generation failure
4. Run full Playwright E2E suite — must pass 100%
5. **After E2E passes only:** `git add` + commit "chore: pre-cutover checkpoint"
6. Update `src/api/main.py`: change `/` route to 301 redirect → `/chat`
7. Delete `web/templates/index.html`
8. Delete `web/static/app.js`
9. Delete `web/static/styles.css`
10. Update README with new `/chat` as primary URL
11. Run server, open browser, verify `/` redirects to `/chat`, all features work

**DoD:**
- `http://localhost:8000/` redirects to `http://localhost:8000/chat`
- All 18 skills accessible via chat
- No reference to legacy files anywhere
- README updated

---

### Phase I — Polish

**Tasks:**
1. Framer Motion: add stagger animations to skill card lists, page transitions
2. Dark mode: full pass — verify all shadcn components respect dark mode
3. Mobile: Sidebar as Sheet `<1024px`, RightDrawer as bottom Sheet `<768px`
4. Code splitting: each skill card as lazy `React.lazy(() => import(...))`
5. Performance: `useCallback`/`useMemo` for heavy renders (timeline, table sorts)
6. Accessibility: `aria-label` on all icon buttons, keyboard navigation in pipeline steps
7. `npm run build` → check bundle sizes (target: main chunk < 200KB gzip)

---

## 15. Browser Test Protocol (mandatory per phase)

> **RULE: No phase is complete until ALL tests below pass in an actual Chromium browser. TypeScript compilation passing is NOT sufficient.**

### After Phase A
- [ ] `http://localhost:8000/chat` loads the React app (not 404, not blank)
- [ ] Arabic text displays with Tajawal font (check DevTools → Network → Fonts)
- [ ] `<html dir="rtl">` in page source
- [ ] Tailwind styles visible (not un-styled HTML)
- [ ] No errors in DevTools Console
- [ ] `/api/tasks` request succeeds (proxy working)

### After Phase B
- [ ] `POST /api/intent` with `{"message": "ابحث عن react"}` returns `{ intent: "research" }`
- [ ] `POST /api/chat` with simple goal returns `{ mode: "single", task_id }`
- [ ] All existing skills still work (test each via `/api/run` curl)
- [ ] `pytest tests/` passes 100%

### After Phase C
- [ ] Type a goal → `AgentRunCard` appears immediately (skeleton/loading state)
- [ ] Live screenshot appears in RightDrawer as agent runs
- [ ] Timeline strip shows each step
- [ ] `SkillBadge` shows correct skill for "ابحث عن python"
- [ ] Override dropdown changes the badge
- [ ] `/search` slash command forces search skill
- [ ] `ContinuationCard` appears after task_end
- [ ] Sidebar shows task history
- [ ] Dark mode toggle: all components switch correctly
- [ ] Resize window to 900px: Sidebar collapses to hamburger

### After Phase D (per card)
- [ ] Send a message triggering this skill → card renders
- [ ] Live events appear during execution (not just at the end)
- [ ] Final result is correct and complete
- [ ] Download button produces a valid file
- [ ] Card renders in failed state (kill server mid-task, verify)

### After Phase E
- [ ] Send: "ابحث عن منافسين عقارات وحلّل مواقعهم وسجّل دخول" → pipeline plan appears
- [ ] Plan shows 3+ steps correctly labeled
- [ ] [▶ تشغيل] starts execution
- [ ] Steps update live (pending → running → done)
- [ ] Force a failure (bad URL) → step goes rose, retry/skip/abort appears
- [ ] [إلغاء] cancels the pipeline cleanly

### After Phase F (per skill)
- [ ] Trigger the skill → card renders with real LLM output
- [ ] HTML artifact: iframe renders, no sandbox CSP errors in console
- [ ] Mermaid: diagram renders as SVG
- [ ] Code: syntax highlighting correct for the language
- [ ] Download: produces valid file that opens correctly

### After Phase G
- [ ] Drag an image onto Composer → preview appears
- [ ] Submit with attachment → shown in thread
- [ ] SettingsPage: providers load, test button works
- [ ] Archive suggestion banner appears for a repeated goal

### After Phase H
- [ ] `http://localhost:8000/` → 301 redirect to `/chat`
- [ ] All 18 skills accessible via chat
- [ ] Legacy files gone from filesystem

---

## 16. Execution Contract — Mandatory Rules

> These rules apply to EVERY task in every phase. The executing agent MUST follow all rules. Violations block the phase from completing.

### 16.1 Code quality rules
```
RULE-01  Never use `any` type in TypeScript. Use `unknown` + type guards.
RULE-02  Every component must handle three states: loading, error, empty — always all three.
RULE-03  Every REST call in React must have try/catch with Arabic error display in the UI.
RULE-04  Every async useEffect must have a cleanup (return () => { ... }).
RULE-05  Never use !important in CSS or inline styles for layout — use Tailwind utilities only.
RULE-06  Never write a TODO comment and move on — finish the feature before touching the next task.
RULE-07  Dark mode and RTL must be verified for every component before marking it done.
RULE-08  TypeScript strict mode must stay ON — tsc --noEmit must pass after every task.
RULE-09  No console.error or unhandled promise rejections left in committed code.
RULE-10  HtmlSandbox iframe must always include sandbox + referrerPolicy attributes — no exceptions.
```

### 16.2 Testing rules
```
RULE-11  Browser verification is MANDATORY after each phase. Compilation is not enough.
RULE-12  Every WebSocket event handler must have an explicit else branch logging unknown events.
RULE-13  useTaskStream must be tested with: new task, already-completed task, mid-run reconnect.
RULE-14  Each skill card must be tested with real backend data, not mocked fixtures.
RULE-15  Pipeline E2E must be tested with an actual compound goal, not mocked pipeline state.
```

### 16.3 Feature completeness rules
```
RULE-16  No feature may be stubbed or marked "TODO for later" unless explicitly listed in Non-Goals (§18).
RULE-17  Every artifact kind must produce a real downloadable file — not a placeholder.
RULE-18  ContinuationCard suggestions must come from the LLM continuation prompt, not hardcoded strings.
RULE-19  Every skill must return summary_ar — empty string is NOT acceptable.
RULE-20  Skill prompt migration (§4.2) must be complete BEFORE writing any frontend for that skill.
```

### 16.4 Commit strategy
```
RULE-21  One git commit per atomic task.
RULE-22  Commit format: feat(phase-X): implement <component> — <what it does in 1 line>
RULE-23  Never commit code that fails tsc --noEmit or causes runtime errors on page load.
RULE-24  Run npm run build before committing Phase C and later tasks.
RULE-25  Never force-push. Never skip hooks (--no-verify).
```

### 16.5 Backend rules
```
RULE-26  All new FastAPI routes must use typed Pydantic request/response models.
RULE-27  All new backend routes must return Arabic error messages in { detail: str (ar) } on 4xx/5xx.
RULE-28  orchestrator.py must have a test for is_compound_heuristic() before it handles live traffic.
RULE-29  prompt_loader.py must raise FileNotFoundError with a helpful message if the prompt file is missing.
RULE-30  Artifact files must be persisted to outputs/artifacts/{task_id}/ before the WS event is emitted.
```

---

## 17. Sequential Task Manifest

> Complete ordered task list for the execution agent. Follow in sequence. Never skip.
> Each task has: ID | Phase | What | File(s) touched | BLOCKING — list of rules that must pass before commit.

```
╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE A — SCAFFOLDING                               ║
╚═══════════════════════════════════════════════════════════════════════╝

A-01  Create Vite+React+TS project
      ACTION: npm create vite@latest web-chat -- --template react-ts
      FILE:   web-chat/ (new directory)
      BLOCK:  npm run dev must start without errors

A-02  Install all frontend dependencies
      ACTION: npm install (full list from §3.1 — all in one command)
      FILE:   web-chat/package.json
      BLOCK:  no peer-dep warnings that block build

A-03  Configure vite.config.ts
      FILE:   web-chat/vite.config.ts
      MUST:   base: '/chat/'
              proxy: { '/api': 'http://localhost:8000', '/ws': 'ws://localhost:8000' }
              build.outDir: '../web/static/chat'
      BLOCK:  npm run build succeeds; GET /chat/assets/* in browser returns files (not 404)

A-04  Configure tsconfig.json
      FILE:   web-chat/tsconfig.json
      MUST:   "strict": true, paths: { "@/*": ["./src/*"] }
      BLOCK:  RULE-08

A-05  Configure tailwind.config.ts + globals.css
      FILE:   web-chat/tailwind.config.ts, web-chat/src/styles/globals.css
      MUST:   fontFamily arabic/sans/mono, RTL utilities, dark mode: 'class'
      BLOCK:  RULE-07

A-06  Initialize shadcn/ui
      ACTION: npx shadcn-ui@latest init (choose: neutral, no CSS variables)
      FILE:   web-chat/components.json, web-chat/src/components/ui/
      BLOCK:  at least Button, Card, Badge import without errors

A-07  Write index.html
      FILE:   web-chat/index.html
      MUST:   <html dir="rtl" lang="ar">, Tajawal preconnect, @fontsource imports in main.tsx
      BLOCK:  DevTools → Network shows Tajawal font loading

A-08  Add /chat mount in FastAPI
      FILE:   src/api/main.py
      MUST:   StaticFiles mounting web/static/chat/ at /chat; SPA fallback (index.html for all sub-paths)
      BLOCK:  GET http://localhost:8000/chat returns 200 (after npm run build)

A-09  Write placeholder ChatPage.tsx
      FILE:   web-chat/src/routes/ChatPage.tsx
      MUST:   Shows Arabic placeholder text; no errors
      BLOCK:  RULE-08, RULE-09

A-10  BROWSER VERIFICATION (Phase A DoD)
      Open: http://localhost:8000/chat
      VERIFY: All Phase A browser checks from §15 pass ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE B — BACKEND                                   ║
╚═══════════════════════════════════════════════════════════════════════╝

B-01  Create prompts/ directory + extract planner prompt
      FILE:   prompts/planner.md (English, {locale} token)
      UPDATE: src/core/planner.py → use load_prompt()
      BLOCK:  Server restarts without ImportError; planner still works

B-02  Extract decider + critic + perception prompts
      FILE:   prompts/decider.md, prompts/critic.md
      UPDATE: src/core/agent.py, src/core/critic.py, src/core/perception.py
      BLOCK:  Existing /api/run still works end-to-end

B-03  Extract synthesizer + verifier prompts
      FILE:   prompts/synthesizer.md, prompts/verifier.md
      UPDATE: src/core/search_agent.py, src/core/verifier.py
      BLOCK:  Research skill still returns cited synthesis

B-04  Extract skill-specific prompts (explore, find_components, design_tokens, clone)
      FILE:   prompts/skills/explore.md, find_components.md, design_tokens.md, clone.md
      UPDATE: src/skills/explore.py, find_components.py, design_tokens.py, clone.py
      BLOCK:  Each skill still produces correct output

B-05  Write prompt_loader.py
      FILE:   src/core/prompt_loader.py
      MUST:   Raises FileNotFoundError with helpful message for missing files (RULE-29)
              locale injection works for both "ar" and "en"
      BLOCK:  tests/test_prompt_loader.py passes

B-06  Write Artifact model
      FILE:   src/core/artifacts.py
      MUST:   Full Pydantic model per §4.1
      BLOCK:  RULE-08 equivalent (mypy clean)

B-07  Write orchestrator.py (core)
      FILE:   src/core/orchestrator.py
      MUST:   plan(), run(), is_compound_heuristic(), _resolve_params(), _fan_out() (cap=5)
              $askUser emits pipeline_paused with required_fields[] (G06)
      BLOCK:  tests/test_orchestrator.py passes (plan parsing, param resolution, compound heuristic)

B-08  Create src/api/routes/ package
      FILE:   src/api/routes/__init__.py
      BLOCK:  No import errors

B-09  Write routes/intent.py
      FILE:   src/api/routes/intent.py
      MUST:   POST /api/intent → { intent, confidence, missing_params[], is_compound (heuristic only) }
              RULE-26, RULE-27
      BLOCK:  curl POST /api/intent returns correct JSON

B-10  Write routes/chat.py
      FILE:   src/api/routes/chat.py
      MUST:   POST /api/chat → routes to single skill OR orchestrator based on compound check
              Returns { mode: "single"|"pipeline"|"need_params", task_id?, pipeline_id?, missing_params? }
      BLOCK:  Simple goal → mode: "single" + task_id; compound goal → mode: "pipeline" + pipeline_id

B-11  Write routes/uploads.py
      FILE:   src/api/routes/uploads.py
      MUST:   POST /api/uploads multipart → saves to outputs/uploads/{uuid}/ → returns Attachment metadata
              RULE-26, RULE-27
      BLOCK:  curl upload a file → response has url that serves the file

B-12  Write routes/artifacts.py
      FILE:   src/api/routes/artifacts.py
      MUST:   GET /api/artifacts/{id} → metadata
              GET /api/artifacts/{id}/preview → inline content
              GET /api/artifacts/{id}/download → Content-Disposition attachment (G15 — ZIP support)
              POST /api/artifacts/{id}/regenerate → triggers re-run
      BLOCK:  Can upload + download a file round-trip

B-13  Write routes/continuation.py
      FILE:   src/api/routes/continuation.py
      MUST:   GET /api/continuation/{id} → { suggestions: [{ label_ar, prompt }] }
              Async — uses prompts/continuation.md + task context to generate via LLM
              2s timeout: returns empty suggestions if LLM too slow (G18)
      BLOCK:  Returns JSON within 3s for any task_id

B-14  Add pipeline + completion_prompt WS events to event bus
      FILE:   src/core/event_bus.py (or wherever events are published)
      BLOCK:  Server starts without errors; existing WS events still work

B-15  Wire all new routes into main.py
      FILE:   src/api/main.py
      BLOCK:  All 11 new endpoints return non-404

B-16  Write all backend tests
      FILE:   tests/test_orchestrator.py, tests/test_prompt_loader.py, tests/test_artifacts.py
      BLOCK:  pytest tests/ → 100% pass

B-17  BROWSER/API VERIFICATION (Phase B DoD)
      Verify all Phase B checks from §15 pass ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE C — CORE CHAT SHELL                           ║
╚═══════════════════════════════════════════════════════════════════════╝

C-01  Write lib/events.ts         ALL WS event TypeScript types
C-02  Write lib/api.ts            apiFetch<T>, apiPost<T>, typed endpoints (RULE-03, RULE-13)
C-03  Write hooks/useTaskStream.ts full reconnect + late-join + backoff (G05, §12)
C-04  Write lib/runtime-adapter.ts assistant-ui LocalRuntime adapter (G04, §3.2)
C-05  Write components/layout/AppShell.tsx
C-06  Write components/layout/Sidebar.tsx   task history, settings link, new-chat button
C-07  Write components/layout/TopBar.tsx    locale toggle, theme toggle
C-08  Write components/layout/RightDrawer.tsx  collapsible; open only during execution
C-09  Write components/chat/EmptyState.tsx  greeting + 6 quick-start chips
C-10  Write components/chat/MessageBubble.tsx  user + assistant variants
C-11  Write components/chat/ChatThread.tsx  AssistantRuntimeProvider wrapper
C-12  Write components/chat/Composer.tsx   textarea + send + attachment + slash commands
C-13  Write hooks/useIntent.ts     debounced /api/intent, 300ms (G07)
C-14  Write components/chat/SkillBadge.tsx  badge + 18-skill override dropdown
C-15  Write components/live/ActionIcon.tsx  icon map (port from app.js describeAction)
C-16  Write components/live/TimelineStrip.tsx accordion step list
C-17  Write components/live/LiveScreenshot.tsx  screenshot display in RightDrawer
C-18  Write components/skill-cards/AgentRunCard.tsx  generic task card
C-19  Write components/chat/ContinuationCard.tsx  completion + suggestions + buttons
C-20  Wire ChatPage.tsx composing all components
C-21  Set up react-router-dom in App.tsx  (/chat, /chat/settings, /chat/artifacts)
C-22  Add locales/ar.json + locales/en.json  (port all Arabic labels from legacy index.html)
C-23  BROWSER VERIFICATION — ALL Phase C checks from §15 ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE D — EXISTING SKILL CARDS (10)                 ║
╚═══════════════════════════════════════════════════════════════════════╝

D-01  SearchResultCard + update search_agent.py return value
D-02  ExploreReportCard + update explore.py (MD artifact)
D-03  DesignTokensCard + update design_tokens.py (Tailwind config artifact)
D-04  ComponentsGalleryCard + update find_components.py
D-05  LoginCard + update login.py
D-06  SignupCard + update signup.py
D-07  TempSignupCard + update temp_signup.py
D-08  CloneCard + update clone.py (iframe preview + PDF artifact)
D-09  SiteCloneCard + update site_clone.py (ZIP artifact)
D-10  Refine AgentRunCard with all perception/decision/action event types
D-11  BROWSER VERIFICATION — each card per §15 Phase D checks ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE E — PIPELINE UI                               ║
╚═══════════════════════════════════════════════════════════════════════╝

E-01  Write components/pipeline/PipelineStep.tsx
E-02  Write components/pipeline/PipelineCard.tsx
E-03  Write components/pipeline/PipelineApproval.tsx
E-04  Write hooks/usePipeline.ts
E-05  Wire pipeline_paused required_fields form (G06)
E-06  Update ChatPage to handle pipeline_id response from /api/chat
E-07  BROWSER VERIFICATION — full pipeline E2E per §15 Phase E checks ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE F — NEW SKILLS (8)                            ║
╚═══════════════════════════════════════════════════════════════════════╝

F-01  md_writer: backend + ArtifactPanel + ArtifactActions + MarkdownArtifactCard
F-02  html_artifact: backend + HtmlSandbox (CSP per §7) + HtmlArtifactCard
F-03  code_artifact: backend + CodeBlock (shiki) + CodeArtifactCard
F-04  mermaid_diagram: backend + mermaid.js render + MermaidArtifactCard
F-05  pdf_export: client-side @react-pdf/renderer + PdfArtifactCard
F-06  summarize: backend + SummarizeCard
F-07  translate: backend + TranslateCard
F-08  competitor_matrix: backend + sortable table + CSV export + CompetitorMatrixCard
F-09  BROWSER VERIFICATION — each new skill per §15 Phase F checks ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE G — SETTINGS + ATTACHMENTS                    ║
╚═══════════════════════════════════════════════════════════════════════╝

G-01  ProvidersPanel.tsx (port from app.js)
G-02  AccountsLedger.tsx (port from app.js)
G-03  ArchiveBrowser.tsx (port from app.js)
G-04  useArchiveSuggestion.ts + ArchiveSuggestionBanner.tsx (G12)
G-05  Composer drag-and-drop + paste handler
G-06  /api/uploads integration + AttachmentPreview.tsx
G-07  BROWSER VERIFICATION — all Phase G checks from §15 ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE H — MIGRATION CUTOVER                         ║
╚═══════════════════════════════════════════════════════════════════════╝

H-01  Full RTL audit (all components — logical properties)
H-02  Keyboard shortcuts (Enter, Shift+Enter, Escape, /)
H-03  Error state verification (network, task failed, WS disconnect, artifact failure)
H-04  Run full Playwright E2E suite — must pass 100%
H-05  git commit "chore: pre-cutover checkpoint"
H-06  Update src/api/main.py: / → 301 → /chat
H-07  Delete web/templates/index.html
H-08  Delete web/static/app.js
H-09  Delete web/static/styles.css
H-10  Update README.md
H-11  BROWSER VERIFICATION — all Phase H checks from §15 ✓

╔═══════════════════════════════════════════════════════════════════════╗
║                   PHASE I — POLISH                                    ║
╚═══════════════════════════════════════════════════════════════════════╝

I-01  Framer Motion animations (stagger, page transitions)
I-02  Dark mode full pass
I-03  Mobile responsive pass (Sidebar → Sheet, Drawer → bottom Sheet)
I-04  Code splitting (React.lazy per skill card)
I-05  Performance pass (useCallback/useMemo heavy renders)
I-06  Accessibility (aria-labels, keyboard nav)
I-07  Bundle size check (main chunk < 200KB gzip target)
I-08  FINAL BROWSER VERIFICATION — all 18 skills, RTL, dark mode, mobile ✓
```

---

## 18. Non-Goals (out of scope — do NOT implement)

- Multi-user authentication
- Voice input/output
- Real-time collaborative artifact editing
- Server-side PDF generation (client-side via `@react-pdf/renderer` is sufficient)
- Token-level LLM streaming (events are step-granular, not token-granular)
- Syntax-highlighted code execution sandbox (Phase F `code_artifact` is display-only; runtime sandbox deferred)
- i18n for any language other than Arabic and English

---

## 19. Approval Checklist (v3 — final)

- [x] Architecture (ADRs 1–10) approved and corrected
- [x] Tech stack corrected (WeasyPrint removed, react-router added, Vitest+Playwright added, @ai-sdk/react usage clarified)
- [x] `Artifact` Pydantic model defined (G08)
- [x] assistant-ui runtime adapter pattern specified (G04)
- [x] WebSocket reconnect + late-join strategy defined (G05)
- [x] `$askUser` / `pipeline_paused` event carries `required_fields[]` (G06)
- [x] Intent detection split: rule-based on typing, LLM only on submit (G07)
- [x] HtmlSandbox security attributes specified (G11)
- [x] ArchiveSuggestion placed in Composer, not SettingsPage (G12)
- [x] Prompt migration map complete (G16)
- [x] ZIP artifact download endpoint added (G15)
- [x] 16 execution contract rules defined
- [x] 5 testing rules defined
- [x] 5 feature completeness rules defined
- [x] 5 backend rules defined
- [x] 62 sequential atomic tasks defined across 9 phases
- [x] Browser test checklist per phase

**Status: HARDENED — READY FOR PHASE A EXECUTION**
Type "ابدأ Phase A" to begin.
