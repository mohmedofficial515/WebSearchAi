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
        # With stealth, navigator.webdriver should be undefined (None) or false —
        # both indicate the automation flag is not set to True.
        # patchright patches at binary level: returns undefined→None or false→False,
        # never the plain True that unpatched Chrome exposes.
        assert webdriver in (None, False), (
            f"navigator.webdriver = {webdriver!r} — stealth patch not applied"
        )
    finally:
        await session.stop()
