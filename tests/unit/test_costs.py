"""Unit tests for Phase 9 — LLM Cost Tracker, TrackingProvider, FailoverProvider."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx


# ── CostEntry ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cost_entry_to_dict_shape():
    from src.llm.costs import CostEntry

    e = CostEntry(
        ts=1000.0, provider="mistral", model="mistral-small-latest",
        input_tokens=100, output_tokens=50, cost_usd=0.000025, endpoint="chat",
    )
    d = e.to_dict()
    assert d["provider"] == "mistral"
    assert d["model"] == "mistral-small-latest"
    assert d["input_tokens"] == 100
    assert d["output_tokens"] == 50
    assert d["cost_usd"] == 0.000025
    assert d["endpoint"] == "chat"
    assert d["ts"] == 1000.0


# ── CostTracker.estimate_cost ─────────────────────────────────────────────────


@pytest.mark.unit
def test_estimate_cost_known_model():
    from src.llm.costs import CostTracker

    ct = CostTracker()
    # mistral-small: $0.0001/1K input, $0.0003/1K output
    cost = ct.estimate_cost("mistral-small-latest", input_tokens=1000, output_tokens=1000)
    assert cost == pytest.approx(0.0004, rel=1e-4)


@pytest.mark.unit
def test_estimate_cost_unknown_model_is_zero():
    from src.llm.costs import CostTracker

    ct = CostTracker()
    assert ct.estimate_cost("some-unknown-model", 500, 500) == 0.0


@pytest.mark.unit
def test_estimate_cost_ollama_is_zero():
    from src.llm.costs import CostTracker

    ct = CostTracker()
    assert ct.estimate_cost("llama3.2", 5000, 5000) == 0.0


@pytest.mark.unit
def test_estimate_cost_embed_only_input():
    from src.llm.costs import CostTracker

    ct = CostTracker()
    # text-embedding-3-small: $0.00002/1K input, $0/1K output
    cost = ct.estimate_cost("text-embedding-3-small", input_tokens=1000, output_tokens=0)
    assert cost == pytest.approx(0.00002, rel=1e-4)


# ── CostTracker.record / read_entries ────────────────────────────────────────


@pytest.mark.unit
def test_record_writes_jsonl(tmp_path: Path):
    from src.llm.costs import CostTracker

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    entry = ct.record(
        provider="mistral", model="mistral-small-latest",
        input_tokens=200, output_tokens=100, endpoint="chat",
    )
    lines = (tmp_path / "costs.jsonl").read_text().splitlines()
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert d["provider"] == "mistral"
    assert d["endpoint"] == "chat"
    assert entry.cost_usd >= 0


@pytest.mark.unit
def test_record_appends_multiple(tmp_path: Path):
    from src.llm.costs import CostTracker

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    for _ in range(3):
        ct.record(provider="openai", model="gpt-4o-mini",
                  input_tokens=100, output_tokens=50, endpoint="chat_json")
    lines = (tmp_path / "costs.jsonl").read_text().splitlines()
    assert len(lines) == 3


@pytest.mark.unit
def test_read_entries_returns_all(tmp_path: Path):
    from src.llm.costs import CostTracker

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    ct.record(provider="a", model="m", input_tokens=1, output_tokens=1, endpoint="chat")
    ct.record(provider="b", model="m", input_tokens=1, output_tokens=1, endpoint="embed")
    entries = ct.read_entries()
    assert len(entries) == 2
    assert entries[0].provider == "a"
    assert entries[1].provider == "b"


@pytest.mark.unit
def test_read_entries_empty_file_returns_empty(tmp_path: Path):
    from src.llm.costs import CostTracker

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    assert ct.read_entries() == []


@pytest.mark.unit
def test_read_entries_since_ts_filters(tmp_path: Path):
    from src.llm.costs import CostTracker, CostEntry

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    path = tmp_path / "costs.jsonl"
    old = CostEntry(ts=1000.0, provider="x", model="m",
                    input_tokens=1, output_tokens=1, cost_usd=0, endpoint="chat")
    new = CostEntry(ts=9000.0, provider="y", model="m",
                    input_tokens=1, output_tokens=1, cost_usd=0, endpoint="chat")
    with path.open("a") as fh:
        fh.write(json.dumps(old.to_dict()) + "\n")
        fh.write(json.dumps(new.to_dict()) + "\n")

    entries = ct.read_entries(since_ts=5000.0)
    assert len(entries) == 1
    assert entries[0].provider == "y"


@pytest.mark.unit
def test_read_entries_skips_malformed_lines(tmp_path: Path):
    from src.llm.costs import CostTracker

    p = tmp_path / "costs.jsonl"
    p.write_text('{"bad": true}\nnot-json\n')
    ct = CostTracker(log_path=p)
    assert ct.read_entries() == []  # both lines are malformed CostEntry data


# ── CostTracker.daily_summary ────────────────────────────────────────────────


@pytest.mark.unit
def test_daily_summary_aggregates_by_day(tmp_path: Path):
    from src.llm.costs import CostTracker, CostEntry

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    path = tmp_path / "costs.jsonl"

    # Two entries on 2026-01-01 UTC, one on 2026-01-02 UTC
    ts_day1a = 1735689600.0   # 2026-01-01 00:00:00 UTC
    ts_day1b = 1735689700.0   # 2026-01-01 00:01:40 UTC
    ts_day2  = 1735776000.0   # 2026-01-02 00:00:00 UTC

    for ts, provider in [(ts_day1a, "a"), (ts_day1b, "b"), (ts_day2, "c")]:
        e = CostEntry(ts=ts, provider=provider, model="gpt-4o-mini",
                      input_tokens=1000, output_tokens=500, cost_usd=0.000525, endpoint="chat")
        with path.open("a") as fh:
            fh.write(json.dumps(e.to_dict()) + "\n")

    summary = ct.daily_summary()
    assert len(summary) == 2
    assert summary[0]["calls"] == 2
    assert summary[1]["calls"] == 1
    assert summary[0]["date"] < summary[1]["date"]


@pytest.mark.unit
def test_daily_summary_empty_no_file(tmp_path: Path):
    from src.llm.costs import CostTracker

    ct = CostTracker(log_path=tmp_path / "costs.jsonl")
    assert ct.daily_summary() == []


# ── TrackingProvider ──────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_tracking_provider_chat_records_cost(tmp_path: Path):
    from src.llm.providers.tracking import TrackingProvider
    from src.llm.costs import CostTracker

    tracker = CostTracker(log_path=tmp_path / "costs.jsonl")

    inner = MagicMock()
    inner.chat = AsyncMock(return_value="Hello world")
    inner._text_model = "mistral-small-latest"

    with patch("src.llm.providers.tracking._tracker", tracker):
        tp = TrackingProvider(inner, "mistral")
        result = await tp.chat([{"role": "user", "content": "hi"}])

    assert result == "Hello world"
    entries = tracker.read_entries()
    assert len(entries) == 1
    assert entries[0].endpoint == "chat"
    assert entries[0].provider == "mistral"


@pytest.mark.unit
async def test_tracking_provider_embed_records_cost(tmp_path: Path):
    from src.llm.providers.tracking import TrackingProvider
    from src.llm.costs import CostTracker

    tracker = CostTracker(log_path=tmp_path / "costs.jsonl")

    inner = MagicMock()
    inner.embed = AsyncMock(return_value=[0.1, 0.2])
    inner._embed_model = "text-embedding-3-small"

    with patch("src.llm.providers.tracking._tracker", tracker):
        tp = TrackingProvider(inner, "openai")
        vec = await tp.embed("test text")

    assert vec == [0.1, 0.2]
    entries = tracker.read_entries()
    assert len(entries) == 1
    assert entries[0].endpoint == "embed"
    assert entries[0].model == "text-embedding-3-small"


@pytest.mark.unit
async def test_tracking_provider_close_delegates():
    from src.llm.providers.tracking import TrackingProvider

    inner = MagicMock()
    inner.close = AsyncMock()
    tp = TrackingProvider(inner, "test")
    await tp.close()
    inner.close.assert_awaited_once()


# ── FailoverProvider ──────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_failover_uses_first_provider_on_success():
    from src.llm.providers.failover import FailoverProvider

    p1 = MagicMock()
    p1.chat = AsyncMock(return_value="from p1")
    p2 = MagicMock()
    p2.chat = AsyncMock(return_value="from p2")

    fp = FailoverProvider([p1, p2])
    result = await fp.chat([{"role": "user", "content": "hi"}])
    assert result == "from p1"
    p2.chat.assert_not_awaited()


@pytest.mark.unit
async def test_failover_advances_on_httpx_429():
    from src.llm.providers.failover import FailoverProvider

    mock_response = MagicMock()
    mock_response.status_code = 429

    p1 = MagicMock()
    p1.chat = AsyncMock(side_effect=httpx.HTTPStatusError("rate limit", request=MagicMock(), response=mock_response))
    p2 = MagicMock()
    p2.chat = AsyncMock(return_value="from p2")

    fp = FailoverProvider([p1, p2])
    result = await fp.chat([{"role": "user", "content": "hi"}])
    assert result == "from p2"


@pytest.mark.unit
async def test_failover_advances_on_rate_limited_string():
    from src.llm.providers.failover import FailoverProvider

    p1 = MagicMock()
    p1.chat = AsyncMock(side_effect=RuntimeError("rate_limited"))
    p2 = MagicMock()
    p2.chat = AsyncMock(return_value="ok")

    fp = FailoverProvider([p1, p2])
    result = await fp.chat([])
    assert result == "ok"


@pytest.mark.unit
async def test_failover_raises_when_all_exhausted():
    from src.llm.providers.failover import FailoverProvider

    mock_response = MagicMock()
    mock_response.status_code = 429

    p1 = MagicMock()
    p1.chat = AsyncMock(side_effect=httpx.HTTPStatusError("rl", request=MagicMock(), response=mock_response))

    fp = FailoverProvider([p1])
    with pytest.raises(httpx.HTTPStatusError):
        await fp.chat([])


@pytest.mark.unit
async def test_failover_reraises_non_429_error():
    from src.llm.providers.failover import FailoverProvider

    p1 = MagicMock()
    p1.chat = AsyncMock(side_effect=ValueError("bad input"))
    p2 = MagicMock()
    p2.chat = AsyncMock(return_value="ok")

    fp = FailoverProvider([p1, p2])
    with pytest.raises(ValueError, match="bad input"):
        await fp.chat([])
    p2.chat.assert_not_awaited()


@pytest.mark.unit
async def test_failover_close_closes_all():
    from src.llm.providers.failover import FailoverProvider

    p1, p2 = MagicMock(), MagicMock()
    p1.close = AsyncMock()
    p2.close = AsyncMock()

    fp = FailoverProvider([p1, p2])
    await fp.close()
    p1.close.assert_awaited_once()
    p2.close.assert_awaited_once()


@pytest.mark.unit
def test_failover_requires_at_least_one_provider():
    from src.llm.providers.failover import FailoverProvider

    with pytest.raises(ValueError):
        FailoverProvider([])


# ── get_provider wraps with TrackingProvider ──────────────────────────────────


@pytest.mark.unit
def test_get_provider_returns_tracking_wrapper():
    from src.llm.providers.auto import get_provider
    from src.llm.providers.tracking import TrackingProvider

    settings = MagicMock()
    settings.llm_provider = "auto"
    settings.mistral_api_key = ""
    settings.openai_api_key = ""
    settings.anthropic_api_key = ""
    settings.ollama_base_url = "http://localhost:11434"

    provider = get_provider(settings)
    assert isinstance(provider, TrackingProvider)


# ── API endpoints ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_api_costs_summary_route_exists():
    from src.api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/costs" in paths


@pytest.mark.unit
def test_api_costs_entries_route_exists():
    from src.api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/costs/entries" in paths
