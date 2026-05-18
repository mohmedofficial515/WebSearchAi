# Changelog

All notable changes to this project will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

### Added
- `docs/` directory with full reference: `ROADMAP`, `ARCHITECTURE`, `API`, `SKILLS`, `CONFIGURATION`, `DEPLOYMENT`, `CONTRIBUTING`, `TROUBLESHOOTING`
- `pyproject.toml` with editable install, dev extras (ruff, pytest, mypy, pre-commit)
- `tests/` scaffolding: `unit/`, `integration/`, shared `conftest.py` with `FakeLLM`
- Initial unit tests for `config`, `event_bus`, `planner`, `verifier`, `executor`
- Initial integration smoke test for `BrowserSession`
- `Dockerfile` (multi-stage, non-root user, healthcheck)
- `docker-compose.yml` (single service + Redis placeholder for Phase 6)
- `.github/workflows/ci.yml` (lint + unit + integration + Docker build)
- `.github/workflows/release.yml` (tag-triggered ghcr.io publish)
- `.github/ISSUE_TEMPLATE/` and `PULL_REQUEST_TEMPLATE.md`
- `Makefile` (Unix) and `scripts/dev.ps1` (Windows) for common tasks
- `scripts/smoke_test.py` — end-to-end server health check
- `scripts/new_skill.py` — skill scaffolding generator
- `.pre-commit-config.yaml` with ruff + gitleaks
- `src/storage/` and `src/memory/` package scaffolding for Phase 2
- `src/llm/providers/` scaffolding for Phase 9
- `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`

### Changed
- `README.md` rewritten to reflect new structure and point at `docs/`

---

## [0.1.0] — 2026-05-17

Initial release — Phase 1 MVP.

### Added
- Plan → Perceive → Decide → Act → Verify agent loop (`src/core/`)
- Playwright stealth browser wrapper with `Sec-Ch-Ua` override
- Mistral text + Pixtral vision LLM client with retries
- 5 skills: `run`, `signup`, `login`, `explore`, `clone`
- FastAPI + WebSocket Web UI at `http://127.0.0.1:8000`
- Typer CLI (`python run.py <command>`)
- Async event bus streaming step-by-step progress
- In-memory task manager with cancel support
- `outputs/` directory layout for sessions, reports, cloned sites
- `install.bat`, `start.bat`, `cli.bat` for Windows
- Tested against `github.com` explore — produces 19-feature structured report

### Fixed
- Extract loop bug — `Executor` notes now contain real evidence, not just the `what` param
- Verifier false negatives on raw-JSON pages — extractions are now primary evidence
- Headless-Chrome leak — `Sec-Ch-Ua` headers overridden to look like real Chrome
- Repeated `extract` actions — Decider prompt now forbids re-extraction
