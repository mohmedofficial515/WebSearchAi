"""Unit tests for src/core/artifacts.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.artifacts import Artifact, artifacts_base


def _make() -> Artifact:
    return Artifact(
        task_id="t1",
        kind="md",
        filename="report.ar.md",
        content_path="report.ar.md",
        mime_type="text/markdown",
        size_bytes=128,
        label_ar="التقرير",
    )


def test_artifact_assigns_uuid_artifact_id() -> None:
    a = _make()
    assert isinstance(a.artifact_id, str)
    assert len(a.artifact_id) == 32  # uuid4 hex
    # ID is unique per instance
    assert _make().artifact_id != a.artifact_id


def test_artifact_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            task_id="t1",
            kind="docx",  # type: ignore[arg-type]
            filename="x",
            content_path="x",
            mime_type="application/octet-stream",
            size_bytes=1,
            label_ar="x",
        )


def test_artifact_absolute_path_uses_task_id() -> None:
    a = _make()
    base = Path("/tmp/out/artifacts")
    p = a.absolute_path(base)
    assert p == base / "t1" / "report.ar.md"


def test_artifacts_base_layout() -> None:
    assert artifacts_base(Path("/tmp/out")) == Path("/tmp/out/artifacts")
