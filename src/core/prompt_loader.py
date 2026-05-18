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

import re
from pathlib import Path

# `prompts/` lives at the repo root, NOT under `src/`. From this file:
#   src/core/prompt_loader.py → ../../prompts/
_BASE = Path(__file__).resolve().parent.parent.parent / "prompts"

# A prompt file may bundle several related sub-prompts (e.g. `critic.md`
# packages rank/content/queries/re_search). Sections are delimited by a
# line matching `## SECTION: <name>` and the body is everything up to the
# next SECTION marker. The text before the first marker is the preamble
# (shared header, locale clause, etc.) and is prepended to every section.
_SECTION_RE = re.compile(r"^##\s*SECTION:\s*(\S+)\s*$", re.MULTILINE)


def load_prompt(
    name: str,
    locale: str = "ar",
    *,
    section: str | None = None,
    **kwargs: object,
) -> str:
    """Read `prompts/{name}.md` and return its content with placeholders filled.

    `name` may be a subpath, e.g. `"skills/explore"` resolves to
    `prompts/skills/explore.md`. Always uses forward slashes.

    If `section` is set, the file is parsed for `## SECTION: <name>`
    markers and only that section's body is returned (the preamble is
    NOT prepended — sections are self-contained on purpose).

    Raises FileNotFoundError if the file does not exist or KeyError if
    the requested section is missing.
    """
    path = _BASE / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    template = path.read_text(encoding="utf-8")
    if section is not None:
        template = _extract_section(template, section, source=str(path))
    # We use str.format so prompts can include {locale}, {goal}, etc.
    # Curly braces meant literally must be escaped as {{ }} in the .md file.
    return template.format(locale=locale, **kwargs)


def _extract_section(text: str, section: str, *, source: str) -> str:
    """Return the body of `## SECTION: <section>` from `text`.

    Raises KeyError if the section is not found.
    """
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) == section:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip() + "\n"
    available = ", ".join(m.group(1) for m in matches) or "(none)"
    raise KeyError(
        f"Section {section!r} not found in {source}. Available: {available}"
    )


def prompts_dir() -> Path:
    """Return the absolute path to the prompts directory."""
    return _BASE


def prompts_dir() -> Path:
    """Return the absolute path to the prompts directory."""
    return _BASE
