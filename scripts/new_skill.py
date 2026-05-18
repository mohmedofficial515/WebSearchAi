"""Scaffold a new skill from the canonical template.

Usage:
    python scripts/new_skill.py <skill_name>
    python scripts/new_skill.py review_amazon_product
"""

from __future__ import annotations

import sys
from pathlib import Path

TEMPLATE = '''\
"""Skill: {description}."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..core.agent import Agent
from ..llm.mistral_client import MistralClient


REPORT_SYSTEM = """You are a careful data extractor.
Given a browser-agent transcript, output JSON shaped exactly:
{{
  "field_a": "...",
  "field_b": [...]
}}
"""


@dataclass
class {ClassName}Result:
    field_a: str
    report: dict
    report_path: str


async def {function_name}(arg1: str) -> {ClassName}Result:
    """{description}.

    Args:
        arg1: TODO describe.
    """
    goal = (
        f"Visit {{arg1}}. TODO describe what to do. "
        "End with a 'done' action whose summary contains the key findings."
    )

    async with Agent() as agent:
        result = await agent.run(goal)

    llm = MistralClient()
    try:
        report = await llm.chat_json(REPORT_SYSTEM, json.dumps(result.to_dict()))
    finally:
        await llm.close()

    out_dir = Path(settings.output_path) / "{function_name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = arg1.replace("https://", "").replace("http://", "").replace("/", "_")[:80]
    path = out_dir / f"{{safe}}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {ClassName}Result(field_a=arg1, report=report, report_path=str(path))
'''


TEST_TEMPLATE = '''\
"""Integration test for {function_name}."""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.slow
async def test_{function_name}_happy_path():
    from src.skills.{function_name} import {function_name}

    result = await {function_name}("https://httpbin.org/get")
    assert result.report_path
    assert result.report is not None
'''


def kebab_to_pascal(name: str) -> str:
    return "".join(p.capitalize() for p in name.replace("-", "_").split("_"))


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/new_skill.py <skill_name>")
        sys.exit(1)

    name = sys.argv[1]
    if not name.replace("_", "").isalnum():
        print("Skill name must be alphanumeric + underscores")
        sys.exit(1)

    root = Path(__file__).resolve().parent.parent
    skill_path = root / "src" / "skills" / f"{name}.py"
    test_path = root / "tests" / "integration" / f"test_{name}.py"

    if skill_path.exists():
        print(f"✗ {skill_path} already exists")
        sys.exit(1)

    desc = f"TODO describe what {name} does"
    skill_path.write_text(
        TEMPLATE.format(
            function_name=name,
            ClassName=kebab_to_pascal(name),
            description=desc,
        )
    )
    test_path.write_text(TEST_TEMPLATE.format(function_name=name))

    print(f"✓ Created {skill_path.relative_to(root)}")
    print(f"✓ Created {test_path.relative_to(root)}")
    print()
    print("Next steps:")
    print(f"  1. Fill in the goal in src/skills/{name}.py")
    print(f"  2. Update REPORT_SYSTEM JSON schema")
    print(f"  3. Wire into src/cli.py (CLI command)")
    print(f"  4. Wire into src/api/main.py (REST endpoint)")
    print(f"  5. Add a Web UI tab if user-facing")
    print(f"  6. Update README.md and docs/SKILLS.md")


if __name__ == "__main__":
    main()
