"""Report formatters — turn TaskResult into human-readable artifacts."""

from .component_viewer import render_viewer
from .markdown_report import render_arabic_report, write_arabic_report

__all__ = ["render_arabic_report", "render_viewer", "write_arabic_report"]
