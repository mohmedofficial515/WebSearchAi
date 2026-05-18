"""Human-like delays, typing, and mouse movement curves."""

from __future__ import annotations

import asyncio
import math
import random
from typing import Iterable

from ..config import settings


async def random_delay(
    min_ms: int | None = None, max_ms: int | None = None
) -> None:
    lo = min_ms if min_ms is not None else settings.min_action_delay_ms
    hi = max_ms if max_ms is not None else settings.max_action_delay_ms
    await asyncio.sleep(random.uniform(lo, hi) / 1000.0)


async def human_type(page, selector: str, text: str) -> None:
    """Type into a selector with per-character jitter (WPM-driven)."""
    wpm = max(60, settings.human_typing_wpm)
    base_delay_s = 60.0 / (wpm * 5)
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char, delay=0)
        jitter = random.uniform(0.6, 1.6)
        await asyncio.sleep(base_delay_s * jitter)
        if random.random() < 0.015:
            await asyncio.sleep(random.uniform(0.15, 0.45))


def bezier_curve(
    start: tuple[float, float], end: tuple[float, float], steps: int = 25
) -> Iterable[tuple[float, float]]:
    """Quadratic bezier with a randomized control point for natural arcs."""
    sx, sy = start
    ex, ey = end
    mx = (sx + ex) / 2 + random.uniform(-60, 60)
    my = (sy + ey) / 2 + random.uniform(-60, 60)
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * mx + t ** 2 * ex
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * my + t ** 2 * ey
        yield x, y


async def human_move_mouse(
    page, target: tuple[float, float], start: tuple[float, float] | None = None
) -> None:
    if start is None:
        start = (random.uniform(50, 300), random.uniform(50, 300))
    steps = random.randint(20, 35)
    for x, y in bezier_curve(start, target, steps):
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.005, 0.018))


async def human_scroll(page, direction: str = "down", amount: int = 600) -> None:
    """Smooth scroll with easing."""
    delta = amount if direction == "down" else -amount
    chunks = random.randint(6, 12)
    per = delta / chunks
    for _ in range(chunks):
        await page.mouse.wheel(0, per * random.uniform(0.7, 1.3))
        await asyncio.sleep(random.uniform(0.04, 0.11))


def jitter(value: float, pct: float = 0.15) -> float:
    return value * random.uniform(1 - pct, 1 + pct)
