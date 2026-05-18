"""Visual regression testing — capture baselines and diff against them."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from ..core.browser import BrowserSession
from ..utils.logger import log

_CHANNEL_THRESHOLD = 10  # per-channel delta to consider a pixel "changed"

try:
    import numpy as np  # type: ignore[import-untyped]
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


@dataclass
class VisualTestResult:
    name: str
    url: str
    baseline_path: str
    current_path: str
    diff_path: str | None
    diff_percent: float
    passed: bool
    threshold: float
    width: int = 0
    height: int = 0
    diff_pixels: int = 0
    total_pixels: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "baseline_path": self.baseline_path,
            "current_path": self.current_path,
            "diff_path": self.diff_path,
            "diff_percent": round(self.diff_percent, 6),
            "passed": self.passed,
            "threshold": self.threshold,
            "width": self.width,
            "height": self.height,
            "diff_pixels": self.diff_pixels,
            "total_pixels": self.total_pixels,
        }


# ── Directory helpers ─────────────────────────────────────────────────────────


def _baselines_dir() -> Path:
    p = settings.output_path / "visual_baselines"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _diffs_dir() -> Path:
    p = settings.output_path / "visual_diffs"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Image comparison ──────────────────────────────────────────────────────────


def _compare_images(
    baseline: "Any",  # PIL.Image.Image
    current: "Any",   # PIL.Image.Image
) -> tuple[int, "Any | None"]:
    """Return (diff_pixel_count, highlighted_diff_image_or_None).

    Uses numpy when available for speed; falls back to pure Pillow.
    """
    from PIL import Image, ImageChops, ImageDraw

    if _HAS_NUMPY:
        b_arr = np.array(baseline, dtype=np.int32)
        c_arr = np.array(current, dtype=np.int32)
        diff = np.abs(b_arr - c_arr)
        mask = np.any(diff > _CHANNEL_THRESHOLD, axis=2)
        diff_pixels = int(np.sum(mask))
        if diff_pixels == 0:
            return 0, None
        highlight = np.array(current.copy())
        highlight[mask] = [255, 0, 0]
        return diff_pixels, Image.fromarray(highlight.astype(np.uint8))
    else:
        diff_raw = ImageChops.difference(baseline, current)
        # Prefer new Pillow ≥ 11 API; fall back gracefully
        try:
            pixel_list = list(diff_raw.get_flattened_data())  # type: ignore[attr-defined]
        except AttributeError:
            pixel_list = list(diff_raw.getdata())  # type: ignore[arg-type]
        diff_pixels = sum(1 for px in pixel_list if any(c > _CHANNEL_THRESHOLD for c in px))
        if diff_pixels == 0:
            return 0, None
        w, _ = baseline.size
        highlight = current.copy()
        draw = ImageDraw.Draw(highlight)
        for idx, px in enumerate(pixel_list):
            if any(c > _CHANNEL_THRESHOLD for c in px):
                draw.point((idx % w, idx // w), fill=(255, 0, 0))
        return diff_pixels, highlight


# ── Public API ────────────────────────────────────────────────────────────────


async def capture_baseline(url: str, name: str, *, headless: bool = True) -> Path:
    """Navigate to *url* and save a baseline screenshot as *name*.png."""
    session = BrowserSession(headless=headless)
    try:
        await session.start()
        await session.goto(url)
        img_bytes = await session.screenshot()
    finally:
        await session.stop()

    out = _baselines_dir() / f"{name}.png"
    out.write_bytes(img_bytes)
    log.info(f"Visual baseline saved: {out}")
    return out


async def compare(
    url: str,
    name: str,
    *,
    threshold: float = 0.01,
    headless: bool = True,
) -> VisualTestResult:
    """Compare a fresh screenshot of *url* against the stored baseline *name*.

    threshold: maximum allowed diff fraction (0.01 == 1 %).
    Raises FileNotFoundError if no baseline exists for *name*.
    Raises RuntimeError if Pillow is not installed.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for visual testing: pip install Pillow") from exc

    baseline_path = _baselines_dir() / f"{name}.png"
    if not baseline_path.exists():
        raise FileNotFoundError(
            f"No baseline found for '{name}'. Run capture_baseline() first."
        )

    session = BrowserSession(headless=headless)
    try:
        await session.start()
        await session.goto(url)
        current_bytes = await session.screenshot()
    finally:
        await session.stop()

    ts = int(time.time())
    current_path = _diffs_dir() / f"{name}_current_{ts}.png"
    current_path.write_bytes(current_bytes)

    baseline_img = Image.open(baseline_path).convert("RGB")
    current_img = Image.open(io.BytesIO(current_bytes)).convert("RGB")

    if baseline_img.size != current_img.size:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        current_img = current_img.resize(baseline_img.size, resample)

    w, h = baseline_img.size
    total_pixels = w * h
    diff_pixels, diff_image = _compare_images(baseline_img, current_img)
    diff_percent = diff_pixels / total_pixels if total_pixels else 0.0

    diff_path: Path | None = None
    if diff_image is not None:
        diff_path = _diffs_dir() / f"{name}_diff_{ts}.png"
        diff_image.save(str(diff_path))

    passed = diff_percent <= threshold
    log.info(
        "Visual test '%s': %s  diff=%.2f%%  threshold=%.2f%%",
        name,
        "PASS" if passed else "FAIL",
        diff_percent * 100,
        threshold * 100,
    )
    return VisualTestResult(
        name=name,
        url=url,
        baseline_path=str(baseline_path),
        current_path=str(current_path),
        diff_path=str(diff_path) if diff_path else None,
        diff_percent=diff_percent,
        passed=passed,
        threshold=threshold,
        width=w,
        height=h,
        diff_pixels=diff_pixels,
        total_pixels=total_pixels,
    )


def list_baselines() -> list[dict[str, Any]]:
    """Return metadata for all stored baselines."""
    p = _baselines_dir()
    return [
        {
            "name": f.stem,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified_at": f.stat().st_mtime,
        }
        for f in sorted(p.glob("*.png"))
    ]


def delete_baseline(name: str) -> bool:
    """Delete baseline *name*. Returns True if the file existed and was removed."""
    p = _baselines_dir() / f"{name}.png"
    if p.exists():
        p.unlink()
        return True
    return False
