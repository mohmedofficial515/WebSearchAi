"""Integration smoke test: start a real browser, navigate to httpbin."""

from __future__ import annotations

import pytest


@pytest.mark.integration
async def test_browser_can_navigate_and_extract_json():
    from src.core.browser import BrowserSession

    session = BrowserSession(headless=True)
    await session.start()
    try:
        await session.goto("https://httpbin.org/get")
        title = await session.title()
        assert title is not None
        # The httpbin page is raw JSON inside <pre>
        body_text = await session.eval_js("document.body.innerText")
        assert '"args"' in body_text
        assert '"url"' in body_text
    finally:
        await session.stop()


@pytest.mark.integration
async def test_browser_stealth_hides_webdriver():
    from src.core.browser import BrowserSession

    session = BrowserSession(headless=True)
    await session.start()
    try:
        await session.goto("about:blank")
        webdriver = await session.eval_js("navigator.webdriver")
        # With stealth, navigator.webdriver should be undefined (None in Python)
        assert webdriver is None
    finally:
        await session.stop()
