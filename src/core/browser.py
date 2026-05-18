"""Patchright-powered browser session with binary-level stealth.

We use `patchright` (a patched Playwright build) instead of vanilla
Playwright + playwright-stealth. patchright:

  - eliminates the CDP `Runtime.enable` leak (the dominant 2026
    detection signal that Cloudflare / Bing / Akamai check),
  - patches the `--enable-automation` / `navigator.webdriver` surface
    at process-launch level instead of via JS overrides,
  - is a drop-in replacement: only the import changes.

Why no custom init script anymore: layering JS-level overrides on
top of binary-level patches creates *inconsistencies* (e.g. an
overridden `navigator.plugins` that contradicts what the real
patched binary returns). CreepJS and Cloudflare specifically flag
that contradiction. Trust the patches.
"""

from __future__ import annotations

import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from patchright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ..config import settings
from ..utils.human_behavior import human_move_mouse, human_scroll, human_type, random_delay
from ..utils.logger import log


# Realistic Chrome 134 user agent. Only used when channel="chrome" is
# unavailable and we fall back to bundled Chromium — Chrome itself
# sets a correct UA automatically.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)


def _chrome_is_installed() -> bool:
    """Detect a real Chrome binary on the host. patchright works best
    when it can drive the real Chrome instead of bundled Chromium
    (TLS / JA4 fingerprint matches a genuine browser)."""
    if shutil.which("chrome") or shutil.which("google-chrome"):
        return True
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
    ):
        if Path(p).exists():
            return True
    return False


@dataclass
class BrowserSession:
    """Owns one patchright stack + page; safe to use across the agent loop."""

    headless: bool = field(default_factory=lambda: settings.browser_headless)
    browser_type: str = field(default_factory=lambda: settings.browser_type)
    user_data_dir: Path | None = None

    _pw: Playwright | None = None
    _browser: Browser | None = None
    _context: BrowserContext | None = None
    page: Page | None = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        engine = getattr(self._pw, self.browser_type)
        viewport = {
            "width": settings.browser_viewport_width,
            "height": settings.browser_viewport_height,
        }

        # patchright's recommended launch args. We deliberately keep this
        # list minimal — every extra flag is another fingerprint the bot
        # detectors can match against.
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
            ],
        }

        # Use the real Chrome binary when present (gives us a genuine
        # JA4 / Sec-CH-UA fingerprint). Fall back to bundled Chromium.
        use_chrome = (
            settings.use_chrome_channel
            and self.browser_type == "chromium"
            and _chrome_is_installed()
        )
        if use_chrome:
            launch_kwargs["channel"] = "chrome"

        if settings.http_proxy:
            launch_kwargs["proxy"] = {"server": settings.http_proxy}

        # Persistent context = a real on-disk Chrome profile. Cookies,
        # MUID, captcha-pass history etc. survive between runs. Bing
        # in particular weights this heavily in its trust score.
        if self.user_data_dir is None:
            self.user_data_dir = (settings.output_path / "browser_profile").resolve()
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        context_kwargs: dict[str, Any] = {
            "user_data_dir": str(self.user_data_dir),
            "viewport": viewport,
            "locale": settings.browser_locale,
            "timezone_id": settings.browser_timezone,
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "no_viewport": False,
        }
        if not use_chrome:
            # Only set a UA manually when we're stuck on bundled Chromium.
            context_kwargs["user_agent"] = _DEFAULT_UA

        self._context = await engine.launch_persistent_context(
            **context_kwargs,
            **launch_kwargs,
        )
        self._browser = None  # persistent contexts don't expose a Browser

        self._context.set_default_timeout(settings.browser_timeout)

        # Block notification/geolocation permission prompts — these are
        # browser-level dialogs that appear outside the DOM and cause click
        # timeouts when the agent tries to interact with elements behind them.
        await self._context.grant_permissions([])

        # Reuse the about:blank page that launch_persistent_context opens,
        # otherwise we leave a dangling tab.
        if self._context.pages:
            self.page = self._context.pages[0]
        else:
            self.page = await self._context.new_page()

        # Auto-dismiss any JS alert/confirm/prompt dialogs.
        # Without this, a page that calls window.alert() or shows a
        # beforeunload dialog will freeze the agent loop forever.
        self.page.on("dialog", lambda d: d.dismiss())

        log.info(
            f"🌐 patchright started "
            f"(channel={'chrome' if use_chrome else 'chromium'}, "
            f"headless={self.headless}, profile={self.user_data_dir.name})"
        )

    async def stop(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        finally:
            self._pw = self._browser = self._context = self.page = None
            log.info("🛑 Browser stopped")

    # ------------------------------------------------------------------
    # High-level actions used by the executor
    # ------------------------------------------------------------------

    async def goto(
        self,
        url: str,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = "load",
    ) -> None:
        assert self.page
        log.info(f"➡️  goto {url}")
        await self.page.goto(url, wait_until=wait_until)
        await random_delay(300, 800)

    async def click(self, selector: str, *, humanize: bool = True) -> None:
        assert self.page
        await self.page.wait_for_selector(selector, state="visible")
        if humanize:
            box = await self.page.locator(selector).first.bounding_box()
            if box:
                target = (
                    box["x"] + box["width"] / 2 + random.uniform(-4, 4),
                    box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                )
                await human_move_mouse(self.page, target)
        await self.page.click(selector)
        await random_delay()

    async def type(self, selector: str, text: str) -> None:
        assert self.page
        await self.page.wait_for_selector(selector, state="visible")
        await self.page.fill(selector, "")
        await human_type(self.page, selector, text)
        await random_delay(150, 500)

    async def press(self, key: str) -> None:
        assert self.page
        await self.page.keyboard.press(key)
        await random_delay(120, 400)

    async def scroll(self, direction: str = "down", amount: int = 600) -> None:
        assert self.page
        await human_scroll(self.page, direction=direction, amount=amount)

    async def wait_for(self, selector: str, timeout: int | None = None) -> None:
        assert self.page
        await self.page.wait_for_selector(
            selector, timeout=timeout or settings.browser_timeout
        )

    async def screenshot(self, path: str | Path | None = None) -> bytes:
        assert self.page
        return await self.page.screenshot(
            path=str(path) if path else None, full_page=False
        )

    async def url(self) -> str:
        assert self.page
        return self.page.url

    async def title(self) -> str:
        assert self.page
        return await self.page.title()

    async def html(self) -> str:
        assert self.page
        return await self.page.content()

    async def eval_js(self, script: str) -> Any:
        assert self.page
        return await self.page.evaluate(script)

    async def dismiss_overlay(self) -> dict[str, Any]:
        """Best-effort overlay / modal / cookie-banner dismissal.

        Tries, in order:
          1. Common close-button selectors (aria-label close/dismiss,
             Bootstrap data-dismiss, .modal-close, .btn-close).
          2. Cookie-consent affirmation buttons (Accept / موافق / قبول).
             Clicking "agree" makes the banner go away without leaving
             us with a half-modal still blocking the DOM.
          3. Generic ×/✕/إغلاق/رفض text buttons.
          4. Keyboard Escape (soft fallback).

        Each click is bounded to a 2-second timeout so a stale selector
        match doesn't burn 30 seconds. Returns {"ok": bool, "via": str};
        never raises — caller treats failure as "still blocked".
        """
        assert self.page
        selectors: list[tuple[str, str]] = [
            # ── ARIA close / dismiss ───────────────────────────────
            ('button[aria-label*="close" i]', "aria-close"),
            ('button[aria-label*="dismiss" i]', "aria-dismiss"),
            ('[role="button"][aria-label*="close" i]', "role-close"),
            ('button[aria-label*="إغلاق"]', "aria-close-ar"),
            ('button[aria-label*="اغلاق"]', "aria-close-ar2"),
            # ── Bootstrap / common close classes ───────────────────
            ('button[data-dismiss="modal"]', "bs-dismiss"),
            ('button[data-bs-dismiss="modal"]', "bs5-dismiss"),
            ('button.modal-close, .modal__close, .modal-close-button', "modal-close-class"),
            ('button.close, .btn-close', "close-class"),
            # ── Cookie-banner affirmations ─────────────────────────
            ('button:has-text("Accept all")', "cookie-accept-en"),
            ('button:has-text("Accept All")', "cookie-accept-en2"),
            ('button:has-text("I agree")', "cookie-agree-en"),
            ('button:has-text("Got it")', "cookie-gotit-en"),
            ('button:has-text("موافق")', "cookie-agree-ar"),
            ('button:has-text("أوافق")', "cookie-agree-ar2"),
            ('button:has-text("قبول")', "cookie-accept-ar"),
            ('button:has-text("بإستمرارك")', "cookie-continue-ar"),
            # ── Generic close-text buttons ─────────────────────────
            ('button:has-text("إغلاق")', "txt-close-ar"),
            ('button:has-text("رفض")', "txt-reject-ar"),
            ('button:has-text("لا شكراً")', "txt-no-thanks-ar"),
            ('button:has-text("لا شكرا")', "txt-no-thanks-ar2"),
            ('button:has-text("لاحقاً")', "txt-later-ar"),
            ('button:has-text("لاحقا")', "txt-later-ar2"),
            ('button:has-text("تخطي")', "txt-skip-ar"),
            ('button:has-text("×")', "txt-x"),
            ('button:has-text("✕")', "txt-x2"),
            ('[role="button"]:has-text("×")', "role-x"),
            ('a:has-text("×")', "link-x"),
        ]
        for sel, label in selectors:
            try:
                loc = self.page.locator(sel)
                if await loc.count() == 0:
                    continue
                # Short timeout — if not actually clickable, move on
                # instead of hanging for 30s on a stale match.
                await loc.first.click(timeout=2000)
                await random_delay(200, 500)
                log.info(f"   ↳ overlay dismissed via {label} ({sel})")
                return {"ok": True, "via": label}
            except Exception:
                continue
        try:
            await self.page.keyboard.press("Escape")
            await random_delay(150, 350)
        except Exception:
            pass
        return {"ok": False, "via": "escape-fallback"}
