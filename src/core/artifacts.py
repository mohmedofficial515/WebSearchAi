"""Artifact model — typed metadata for files emitted by skills and pipelines.

An Artifact is the structured-record half of "the agent produced X". The
actual file lives under `outputs/artifacts/{task_id}/{filename}`; this
record carries the metadata the UI needs to preview, download, or
re-render it.

Every artifact has a stable `artifact_id` (uuid4) so the frontend can
key on it across event-bus updates and downloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# All artifact kinds we currently produce. Frontend MIME-routing keys off
# this enum (see CHAT_UI_PLAN §7 — MIME→component map). Adding a new kind
# requires a matching renderer on the frontend.
ArtifactKind = Literal[
    "md",          # markdown report (e.g. report.ar.md)
    "html",        # standalone HTML (clone output, sandboxed iframe)
    "code",        # source code with a syntax-highlight language
    "mermaid",     # mermaid diagram source
    "pdf",         # PDF (client-rendered via @react-pdf/renderer)
    "zip",         # zipped bundle (site_clone output)
    "json",        # structured JSON (matrices, raw extracts)
    "screenshot",  # PNG screenshot
    "csv",         # tabular export
]


class Artifact(BaseModel):
    """Metadata record for one file produced by a skill or pipeline step."""

    artifact_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    task_id: str
    pipeline_id: str | None = None
    kind: ArtifactKind
    filename: str
    content_path: str
    mime_type: str
    size_bytes: int
    label_ar: str
    language: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def absolute_path(self, base: Path) -> Path:
        """Resolve `content_path` against an artifacts base directory."""
        return base / self.task_id / self.content_path


def artifacts_base(output_path: Path) -> Path:
    """Standard layout: `outputs/artifacts/{task_id}/...`."""
    return output_path / "artifacts"
