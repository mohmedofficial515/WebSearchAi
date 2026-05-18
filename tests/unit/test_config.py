"""Sanity checks on the Settings loader."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_settings_load_with_defaults(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    from src.config import Settings

    s = Settings()
    assert s.mistral_api_key == "test-key"
    assert s.browser_type in {"chromium", "firefox", "webkit"}
    assert s.max_steps_per_task > 0
    assert s.min_action_delay_ms < s.max_action_delay_ms


@pytest.mark.unit
def test_output_path_creates_subdirs(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("MISTRAL_API_KEY", "x")
    from src.config import Settings

    s = Settings()
    p = s.output_path
    assert (p / "sessions").exists()
    assert (p / "reports").exists()
    assert (p / "cloned_sites").exists()
    assert (p / "screenshots").exists()
