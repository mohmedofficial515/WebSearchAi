"""Unit tests for Phase 4 — Visual Diff / visual regression testing."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── VisualTestResult.to_dict ──────────────────────────────────────────────────


@pytest.mark.unit
def test_visual_test_result_to_dict_pass():
    from src.skills.visual_test import VisualTestResult

    r = VisualTestResult(
        name="home",
        url="https://example.com",
        baseline_path="/baselines/home.png",
        current_path="/diffs/home_current.png",
        diff_path="/diffs/home_diff.png",
        diff_percent=0.005,
        passed=True,
        threshold=0.01,
        width=1366,
        height=768,
        diff_pixels=50,
        total_pixels=1049088,
    )
    d = r.to_dict()
    assert d["name"] == "home"
    assert d["passed"] is True
    assert d["diff_percent"] == 0.005
    assert d["width"] == 1366
    assert d["total_pixels"] == 1049088


@pytest.mark.unit
def test_visual_test_result_to_dict_fail():
    from src.skills.visual_test import VisualTestResult

    r = VisualTestResult(
        name="checkout",
        url="https://example.com/checkout",
        baseline_path="/b/checkout.png",
        current_path="/d/checkout_current.png",
        diff_path="/d/checkout_diff.png",
        diff_percent=0.15,
        passed=False,
        threshold=0.01,
    )
    d = r.to_dict()
    assert d["passed"] is False
    assert d["diff_percent"] == 0.15
    assert d["diff_path"] == "/d/checkout_diff.png"


# ── capture_baseline ──────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_capture_baseline_saves_png(tmp_path):
    from src.skills.visual_test import capture_baseline

    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with patch("src.skills.visual_test.BrowserSession") as MockSession, \
         patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        session = MagicMock()
        session.start = AsyncMock()
        session.stop = AsyncMock()
        session.goto = AsyncMock()
        session.screenshot = AsyncMock(return_value=fake_bytes)
        MockSession.return_value = session

        path = await capture_baseline("https://example.com", "home")

    assert path == tmp_path / "home.png"
    assert (tmp_path / "home.png").read_bytes() == fake_bytes
    session.goto.assert_awaited_once_with("https://example.com")


@pytest.mark.unit
async def test_capture_baseline_calls_stop_on_error(tmp_path):
    """BrowserSession.stop() must be called even when goto() raises."""
    from src.skills.visual_test import capture_baseline

    with patch("src.skills.visual_test.BrowserSession") as MockSession, \
         patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        session = MagicMock()
        session.start = AsyncMock()
        session.stop = AsyncMock()
        session.goto = AsyncMock(side_effect=RuntimeError("nav error"))
        session.screenshot = AsyncMock()
        MockSession.return_value = session

        with pytest.raises(RuntimeError, match="nav error"):
            await capture_baseline("https://example.com", "home")

    session.stop.assert_awaited_once()


# ── compare: missing baseline ─────────────────────────────────────────────────


@pytest.mark.unit
async def test_compare_raises_when_no_baseline(tmp_path):
    from src.skills.visual_test import compare

    with patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        with pytest.raises(FileNotFoundError, match="No baseline found"):
            await compare("https://example.com", "ghost")


# ── compare: identical images → PASS ─────────────────────────────────────────


@pytest.mark.unit
async def test_compare_identical_images_passes(tmp_path):
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from src.skills.visual_test import compare

    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    (tmp_path / "home.png").write_bytes(png_bytes)

    with patch("src.skills.visual_test.BrowserSession") as MockSession, \
         patch("src.skills.visual_test._baselines_dir", return_value=tmp_path), \
         patch("src.skills.visual_test._diffs_dir", return_value=tmp_path):
        session = MagicMock()
        session.start = AsyncMock()
        session.stop = AsyncMock()
        session.goto = AsyncMock()
        session.screenshot = AsyncMock(return_value=png_bytes)
        MockSession.return_value = session

        result = await compare("https://example.com", "home", threshold=0.01)

    assert result.passed is True
    assert result.diff_percent == 0.0
    assert result.diff_pixels == 0
    assert result.diff_path is None
    assert result.width == 100
    assert result.height == 100
    assert result.total_pixels == 10_000


# ── compare: very different images → FAIL ────────────────────────────────────


@pytest.mark.unit
async def test_compare_different_images_fails(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image
    from src.skills.visual_test import compare

    img_a = Image.new("RGB", (100, 100), color=(200, 200, 200))
    img_b = Image.new("RGB", (100, 100), color=(10, 10, 10))  # clearly different

    buf_a, buf_b = io.BytesIO(), io.BytesIO()
    img_a.save(buf_a, format="PNG")
    img_b.save(buf_b, format="PNG")

    (tmp_path / "page.png").write_bytes(buf_a.getvalue())

    with patch("src.skills.visual_test.BrowserSession") as MockSession, \
         patch("src.skills.visual_test._baselines_dir", return_value=tmp_path), \
         patch("src.skills.visual_test._diffs_dir", return_value=tmp_path):
        session = MagicMock()
        session.start = AsyncMock()
        session.stop = AsyncMock()
        session.goto = AsyncMock()
        session.screenshot = AsyncMock(return_value=buf_b.getvalue())
        MockSession.return_value = session

        result = await compare("https://example.com", "page", threshold=0.01)

    assert result.passed is False
    assert result.diff_percent > 0.5   # most pixels differ
    assert result.diff_path is not None


# ── compare: threshold boundary ───────────────────────────────────────────────


@pytest.mark.unit
async def test_compare_passes_exactly_at_threshold(tmp_path):
    """diff_percent == threshold → still passes (≤ check)."""
    pytest.importorskip("PIL")
    from PIL import Image
    from src.skills.visual_test import compare, VisualTestResult

    img = Image.new("RGB", (10, 10), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    (tmp_path / "t.png").write_bytes(png_bytes)

    with patch("src.skills.visual_test.BrowserSession") as MockSession, \
         patch("src.skills.visual_test._baselines_dir", return_value=tmp_path), \
         patch("src.skills.visual_test._diffs_dir", return_value=tmp_path):
        session = MagicMock()
        session.start = AsyncMock()
        session.stop = AsyncMock()
        session.goto = AsyncMock()
        session.screenshot = AsyncMock(return_value=png_bytes)
        MockSession.return_value = session

        result = await compare("https://example.com", "t", threshold=0.0)

    assert result.passed is True  # 0.0 <= 0.0


# ── list_baselines ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_list_baselines_returns_all_pngs(tmp_path):
    from src.skills.visual_test import list_baselines

    (tmp_path / "home.png").write_bytes(b"fake")
    (tmp_path / "about.png").write_bytes(b"fake2")
    (tmp_path / "ignored.jpg").write_bytes(b"jpg")  # should be excluded

    with patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        result = list_baselines()

    names = {r["name"] for r in result}
    assert names == {"home", "about"}
    assert all("size_bytes" in r for r in result)
    assert all("modified_at" in r for r in result)


@pytest.mark.unit
def test_list_baselines_empty(tmp_path):
    from src.skills.visual_test import list_baselines

    with patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        result = list_baselines()

    assert result == []


# ── delete_baseline ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_delete_baseline_removes_file(tmp_path):
    from src.skills.visual_test import delete_baseline

    (tmp_path / "home.png").write_bytes(b"fake")

    with patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        ok = delete_baseline("home")

    assert ok is True
    assert not (tmp_path / "home.png").exists()


@pytest.mark.unit
def test_delete_baseline_missing_returns_false(tmp_path):
    from src.skills.visual_test import delete_baseline

    with patch("src.skills.visual_test._baselines_dir", return_value=tmp_path):
        ok = delete_baseline("ghost")

    assert ok is False


# ── API body models ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_visual_baseline_body_defaults():
    from src.api.main import VisualBaselineBody

    body = VisualBaselineBody(url="https://example.com", name="home")
    assert body.url == "https://example.com"
    assert body.name == "home"
    assert body.headless is True


@pytest.mark.unit
def test_visual_compare_body_defaults():
    from src.api.main import VisualCompareBody

    body = VisualCompareBody(url="https://example.com", name="home")
    assert body.threshold == 0.01
    assert body.headless is True


@pytest.mark.unit
def test_visual_compare_body_custom_threshold():
    from src.api.main import VisualCompareBody

    body = VisualCompareBody(url="https://x.com", name="x", threshold=0.05)
    assert body.threshold == 0.05
