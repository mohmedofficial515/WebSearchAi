"""LLM cost tracker — appends JSONL to outputs/costs.jsonl."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# USD per 1K tokens: (input_price, output_price)
_PRICES: dict[str, tuple[float, float]] = {
    # ── Mistral ───────────────────────────────────────────────────────────────
    "mistral-small-latest":       (0.0001,   0.0003),
    "mistral-medium-latest":      (0.0027,   0.0081),
    "mistral-large-latest":       (0.008,    0.024),
    "pixtral-12b-2409":           (0.00015,  0.00015),
    "mistral-embed":              (0.00001,  0.0),
    # ── OpenAI ────────────────────────────────────────────────────────────────
    "gpt-4o-mini":                (0.00015,  0.0006),
    "gpt-4o":                     (0.0025,   0.01),
    "text-embedding-3-small":     (0.00002,  0.0),
    # ── Anthropic ─────────────────────────────────────────────────────────────
    "claude-haiku-4-5-20251001":  (0.0008,   0.004),
    "claude-sonnet-4-6":          (0.003,    0.015),
    "claude-opus-4-7":            (0.015,    0.075),
    # ── Groq (FREE tier — $0 until quota exceeded) ────────────────────────────
    "llama-3.1-8b-instant":       (0.0,      0.0),
    "llama-3.3-70b-versatile":    (0.0,      0.0),
    "mixtral-8x7b-32768":         (0.0,      0.0),
    "gemma2-9b-it":               (0.0,      0.0),
    "llama-3.2-11b-vision-preview": (0.0,    0.0),
    # ── Google Gemini (FREE tier) ─────────────────────────────────────────────
    "gemini-1.5-flash":           (0.0,      0.0),
    "gemini-2.0-flash-exp":       (0.0,      0.0),
    "gemini-1.5-pro":             (0.0,      0.0),
    "text-embedding-004":         (0.0,      0.0),
    # ── Cohere (FREE Trial) ───────────────────────────────────────────────────
    "command-r":                  (0.0,      0.0),
    "command-r-plus":             (0.0,      0.0),
    "embed-multilingual-v3.0":    (0.0,      0.0),
    "embed-english-v3.0":         (0.0,      0.0),
    # ── OpenRouter :free models ───────────────────────────────────────────────
    "meta-llama/llama-3.1-8b-instruct:free":  (0.0, 0.0),
    "meta-llama/llama-3.2-3b-instruct:free":  (0.0, 0.0),
    "google/gemma-2-9b-it:free":              (0.0, 0.0),
    "mistralai/mistral-7b-instruct:free":     (0.0, 0.0),
    "microsoft/phi-3-mini-128k-instruct:free":(0.0, 0.0),
    "qwen/qwen-2-7b-instruct:free":           (0.0, 0.0),
    "deepseek/deepseek-r1:free":              (0.0, 0.0),
    # ── Ollama (local, always free) ───────────────────────────────────────────
    "llama3.2":                   (0.0,      0.0),
    "llava":                      (0.0,      0.0),
    "nomic-embed-text":           (0.0,      0.0),
}


@dataclass
class CostEntry:
    ts: float
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    endpoint: str  # "chat" | "chat_json" | "vision" | "vision_json" | "embed"

    def to_dict(self) -> dict:
        return asdict(self)


class CostTracker:
    """Appends one JSONL line per LLM call; reads back for reporting."""

    def __init__(self, log_path: Path | None = None) -> None:
        self._path = log_path  # None → lazy resolve from settings

    def _get_path(self) -> Path:
        if self._path is not None:
            return self._path
        from ..config import settings  # lazy import avoids circular deps
        return settings.output_path / "costs.jsonl"

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        in_p, out_p = _PRICES.get(model, (0.0, 0.0))
        return round((input_tokens / 1000) * in_p + (output_tokens / 1000) * out_p, 8)

    def record(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        endpoint: str,
    ) -> CostEntry:
        entry = CostEntry(
            ts=time.time(),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self.estimate_cost(model, input_tokens, output_tokens),
            endpoint=endpoint,
        )
        path = self._get_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    def read_entries(self, since_ts: float | None = None) -> list[CostEntry]:
        path = self._get_path()
        if not path.exists():
            return []
        entries: list[CostEntry] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
                e = CostEntry(**d)
                if since_ts is None or e.ts >= since_ts:
                    entries.append(e)
            except Exception:
                pass
        return entries

    def daily_summary(self) -> list[dict]:
        """Aggregate cost entries by UTC date; sorted ascending."""
        from datetime import datetime, timezone

        days: dict[str, dict] = {}
        for e in self.read_entries():
            day = datetime.fromtimestamp(e.ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if day not in days:
                days[day] = {
                    "date": day,
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            days[day]["calls"] += 1
            days[day]["input_tokens"] += e.input_tokens
            days[day]["output_tokens"] += e.output_tokens
            days[day]["cost_usd"] = round(days[day]["cost_usd"] + e.cost_usd, 8)
        return sorted(days.values(), key=lambda d: d["date"])


# Module-level singleton used by TrackingProvider
cost_tracker = CostTracker()
