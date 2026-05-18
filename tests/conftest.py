"""Shared pytest fixtures for all tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio loop policy across the test session."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def outputs_tmp(tmp_path: Path, monkeypatch) -> Path:
    """Redirect OUTPUT_DIR to a tmp dir so tests don't pollute outputs/."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    # Re-import settings if needed
    return tmp_path


@pytest.fixture
def fake_mistral_response() -> dict[str, Any]:
    """A canned Mistral chat response shaped like the real SDK."""
    return {
        "choices": [
            {
                "message": {
                    "content": '{"action":"done","summary":"ok"}',
                    "role": "assistant",
                }
            }
        ]
    }


class FakeLLM:
    """In-memory LLM stub for unit-testing planner/decider/verifier without HTTP."""

    def __init__(self, responses: list[dict | str] | None = None):
        self._responses = responses or []
        self.calls: list[dict[str, Any]] = []

    async def chat(self, system: str, user: str, **_) -> str:
        self.calls.append({"kind": "chat", "system": system, "user": user})
        r = self._responses.pop(0) if self._responses else "(empty)"
        return r if isinstance(r, str) else str(r)

    async def chat_json(self, system: str, user: str, **_) -> dict:
        self.calls.append({"kind": "chat_json", "system": system, "user": user})
        r = self._responses.pop(0) if self._responses else {}
        return r if isinstance(r, dict) else {"raw": r}

    async def vision(self, prompt: str, image_bytes: bytes, **_) -> str:
        self.calls.append({"kind": "vision", "prompt": prompt})
        r = self._responses.pop(0) if self._responses else "(empty)"
        return r if isinstance(r, str) else str(r)

    async def vision_json(self, prompt: str, image_bytes: bytes, **_) -> dict:
        self.calls.append({"kind": "vision_json", "prompt": prompt})
        r = self._responses.pop(0) if self._responses else {}
        return r if isinstance(r, dict) else {"raw": r}

    async def close(self) -> None:
        pass


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
async def fake_llm_with(responses: list) -> AsyncIterator[FakeLLM]:
    """Use as: @pytest.mark.parametrize('responses', [[...]])."""
    yield FakeLLM(responses)
