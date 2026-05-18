See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the full contributor guide.

Quick start:

```bash
git clone https://github.com/<you>/WebSearchAi.git
cd WebSearchAi
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
python -m playwright install chromium
pytest tests/unit -q
```

Before opening a PR:

```bash
make format && make lint && make test
```

(On Windows: `./scripts/dev.ps1 format`, `lint`, `test`.)
