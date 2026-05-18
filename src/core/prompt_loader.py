"""Load Markdown-based prompt templates from the `prompts/` directory.

Every LLM-facing prompt in the project lives in a `.md` file under
`prompts/` so it can be edited without touching Python. Templates may
contain `{locale}` (ISO 639-1 code) and arbitrary `{kwarg}` placeholders
that are filled by `str.format(...)` at load time.

Files are read fresh on every call — prompts are small (KB range), so we
favor live-edit ergonomics over caching. If that becomes a hotspot we
can add an LRU cache here without touching callers.
"""

from __future__ import annotations

from pathlib import Path

# `prompts/` lives at the repo root, NOT under `src/`. From this file:
#   src/core/prompt_loader.py → ../../prompts/
_BASE = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str, locale: str = "ar", **kwargs: object) -> str:
    """Read `prompts/{name}.md` and return its content with placeholders filled.

    `name` may be a subpath, e.g. `"skills/explore"` resolves to
    `prompts/skills/explore.md`. Always uses forward slashes.

    Raises FileNotFoundError if the file does not exist.
    """
    path = _BASE / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    template = path.read_text(encoding="utf-8")
    # We use str.format so prompts can include {locale}, {goal}, etc.
    # Curly braces meant literally must be escaped as {{ }} in the .md file.
    return template.format(locale=locale, **kwargs)


def prompts_dir() -> Path:
    """Return the absolute path to the prompts directory."""
    return _BASE
