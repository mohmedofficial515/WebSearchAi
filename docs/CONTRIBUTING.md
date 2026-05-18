# 🤝 Contributing to WebSearchAi

Thanks for considering a contribution. This doc is short on ceremony, long on actually-useful guidance.

---

## 🎯 What we want

| Yes please | No thanks |
|---|---|
| New skills (under `src/skills/`) | Captcha solvers |
| Bug fixes with a regression test | Untested refactors of `core/` |
| Better stealth techniques | Anything that auto-rotates IPs |
| Docs, examples, screencasts | Random additions to `requirements.txt` |
| Performance improvements (with before/after numbers) | "Add feature X because it's cool" |

When in doubt: open an issue first to discuss scope.

---

## 🛠️ Setup

```bash
# 1. fork + clone
git clone https://github.com/<you>/WebSearchAi.git
cd WebSearchAi

# 2. install
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Unix
pip install -e ".[dev]"
python -m playwright install chromium

# 3. configure
cp .env.example .env             # add your Mistral key

# 4. verify
pytest tests/unit -q
python serve.py                  # smoke test the API
```

---

## 🧪 Running tests

```bash
# Unit tests only (fast, mocked LLM + mocked HTTP)
pytest tests/unit -q

# Integration (runs real Playwright on httpbin)
pytest tests/integration -q

# Full suite + coverage
pytest --cov=src --cov-report=term-missing

# One file
pytest tests/unit/test_planner.py -v
```

CI runs `tests/unit` on every PR. `tests/integration` runs nightly.

---

## 🎨 Style

- **Formatting:** `ruff format` (Black-compatible, 88 cols)
- **Linting:** `ruff check`
- **Types:** `mypy src` — we aim for full coverage in `core/` and `llm/`; skills are looser
- **Imports:** `from __future__ import annotations` at top of every module
- **Async everywhere** in core / skills / api — no sync `requests`

One command runs them all:

```bash
make lint       # or: ruff check && ruff format --check && mypy src
```

Format before committing:

```bash
make format     # or: ruff format src tests
```

---

## ✅ PR checklist

- [ ] New code has a test
- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Docs updated if behavior changed (`README.md`, `docs/`, or `.env.example`)
- [ ] `CHANGELOG.md` has a one-line entry under `## [Unreleased]`
- [ ] Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, etc.)

---

## 🌳 Branching

- `main` — always green, deployable
- Feature branches: `feat/<short-name>` or `fix/<issue-number>`
- PRs target `main` directly (no `develop` branch)
- Squash-merge by default

---

## 🐛 Reporting bugs

Open an issue with:

1. **What happened** — including the goal you gave it
2. **What you expected**
3. **Logs** — relevant lines from `outputs/websearchai.log` (with API keys redacted!)
4. **Screenshots** — from `outputs/sessions/<task_id>/`
5. **Environment** — OS, Python version, Playwright version

A bug report with all five gets fixed roughly 10× faster than one without.

---

## 💡 Proposing a new skill

Before writing code:

1. Open an issue titled `Skill proposal: <name>`
2. Describe the goal in one paragraph
3. Sketch the input params and output shape
4. List one or two test sites it should work on

We'll either green-light it, suggest scope changes, or explain why it's out of scope (see [ROADMAP § Out of scope](ROADMAP.md#-out-of-scope-deliberately)).

Then read [`docs/SKILLS.md`](SKILLS.md) for the implementation walkthrough.

---

## 🔐 Security

If you find a vulnerability (e.g., a way for one user's task to read another user's data, prompt injection that escapes the sandbox, etc.):

**Do not open a public issue.** Email the maintainer directly. We'll respond within 72 hours.

---

## 📜 License

By contributing, you agree your code is released under the MIT license (see `LICENSE`).

---

## 🙏 Code of conduct

Be kind, be specific, assume good intent. PR review comments are about the code, not the author.

That's it. Welcome aboard.
