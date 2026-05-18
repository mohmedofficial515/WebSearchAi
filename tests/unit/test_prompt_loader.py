"""Unit tests for src/core/prompt_loader.py."""

from __future__ import annotations

import pytest

from src.core.prompt_loader import load_prompt, prompts_dir


def test_load_planner_prompt_injects_locale() -> None:
    text = load_prompt("planner", locale="en")
    assert "preferred locale is \"en\"" in text
    text_ar = load_prompt("planner", locale="ar")
    assert "preferred locale is \"ar\"" in text_ar


def test_load_missing_prompt_raises_filenotfound() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")


def test_load_section_returns_only_that_section() -> None:
    rank = load_prompt("critic", section="rank")
    assert "score web-search candidates" in rank.lower()
    assert "judge whether a fetched web page" not in rank.lower()


def test_load_missing_section_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        load_prompt("critic", section="nonexistent_section")


def test_prompts_dir_points_at_repo_prompts() -> None:
    p = prompts_dir()
    assert p.name == "prompts"
    assert (p / "planner.md").exists()
    assert (p / "critic.md").exists()
    assert (p / "decider.md").exists()
    assert (p / "skills" / "explore.md").exists()
