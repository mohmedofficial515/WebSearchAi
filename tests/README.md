# Tests

```bash
# fast unit tests — no network, no browser
pytest tests/unit -q

# integration — needs Playwright + internet (uses httpbin.org)
pytest tests/integration -q

# full suite with coverage
pytest --cov=src --cov-report=term-missing
```

## Layout

- `tests/unit/` — hermetic, mocked LLM and browser. Should run in < 5 s.
- `tests/integration/` — real Playwright against `httpbin.org`. Marked `@pytest.mark.integration`.
- `tests/fixtures/` — static HTML / JSON for offline integration tests.
- `tests/conftest.py` — `FakeLLM`, output directory redirection, asyncio config.

## Markers

| Marker | What it means |
|---|---|
| `unit` | No I/O, mocks only |
| `integration` | Real browser, may need network |
| `slow` | Takes > 10 s |
| `e2e` | Hits real external sites — opt-in |

Skip the slow lane:
```bash
pytest -m "not slow and not e2e"
```
