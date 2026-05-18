"""Unified logger using rich for colored, structured output."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from rich.logging import RichHandler

from ..config import settings


def get_logger(name: str = "WebSearchAi") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    rich_handler = RichHandler(rich_tracebacks=True, show_time=True, show_path=False)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    log_file = settings.output_path / "websearchai.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    return logger


log = get_logger()
