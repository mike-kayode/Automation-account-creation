import os
import shutil
import socket
import urllib.request
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


def _find_chrome(explicit: Path | None) -> str | None:
    if explicit and explicit.exists():
        return str(explicit)
    found = shutil.which("chrome")
    if found:
        return found
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(c).exists():
            return c
    local = Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"
    return str(local) if local.exists() else None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _cdp_ok(endpoint: str) -> bool:
    base = endpoint.rstrip("/")
    for path in ("/json/version", "/json/list"):
        try:
            with urllib.request.urlopen(base + path, timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False


class BrowserManager:
    """Attach-first: reuse your already-open real Chrome tab.

    Fast path: if Chrome already listens on the CDP endpoint -> attach
    instantly and reuse the Exness tab (no new login, no new window).
    Else -> clear one-click instruction to enable it (Chrome requires a
    restart with --remote-debugging-port; it cannot be injected into a
    running normal instance). Your tabs/logins are preserved by Chrome
    restore on restart.
    """

    def __init__(self, profile_path: str | Path, navigation_timeout_ms: int,
                 browser_channel: str = "chrome",
                 executable_path: str | Path | None = None,
                 mode: str = "attach",
                 cdp_endpoint: str = "http://127.0.0.1:9222"):
        self.profile_path = Path(profile_path)
        self.navigation_timeout_ms = navigation_timeout_ms
        self.browser_channel = browser_channel
        self.executable_path = Path(executable_path) if executable_path else None
        self.mode = str(mode or "attach").lower()
        self.cdp_endpoint = (cdp_endpoint or "http://127.0.0.1:9222").rstrip("/")
        self._playwright = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def start(self) -> Page:
        self._playwright = await async_playwright().start()
        if self.mode == "launch":
            return await self._start_launch()
        return await self._start_attach_auto()

    def _timeouts(self, ctx: BrowserContext) -> None:
        ctx.set_default_navigation_timeout(self.navigation_timeout_ms)
        ctx.set_default_timeout(self.navigation_timeout_ms)

    def _ensure_debugging(self) -> None:
        if _cdp_ok(self.cdp_endpoint):
            return
        raise RuntimeError(
            f"Chrome CDP is unavailable at {self.cdp_endpoint}. "
            "Your normal Chrome is running WITHOUT --remote-debugging-port, so the "
            "worker cannot attach to it (Chrome does not allow adding debug mode "
            "to an already-running normal window). Your normal Chrome was left "
            "untouched. Fix: keep it open, then in a NEW terminal run "
            "powershell -ExecutionPolicy Bypass -File tools/launch_chrome_debug.ps1 "
            "to open a SEPARATE debug Chrome window, log in to Exness there, "
            "and run py main.py again."
        )

    async def _pick_page(self) -> Page:
        assert self._browser is not None
        all_pages: list[Page] = []
        for ctx in self._browser.contexts:
            all_pages.extend(list(ctx.pages))
        for p in all_pages:  # prefer exact accounts tab
            try:
                u = (p.url or "").lower()
            except Exception:
                continue
            # Skip internal/placeholder targets (chrome://, about:) - their
            # frames can detach at any moment and kill the first goto.
            if u.startswith(("chrome://", "chrome-extension://", "about:", "edge://")):
                continue
            if "exness.com" in u and ("trading/accounts" in u or "pa/" in u):
                self.context = p.context
                self._timeouts(self.context)
                try:
                    await p.bring_to_front()
                except Exception:
                    pass
                return p
        for p in all_pages:  # any exness tab
            try:
                u = (p.url or "").lower()
                if u.startswith(("chrome://", "chrome-extension://", "about:", "edge://")):
                    continue
                if "exness" in u:
                    self.context = p.context
                    self._timeouts(self.context)
                    try:
                        await p.bring_to_front()
                    except Exception:
                        pass
                    return p
            except Exception:
                continue
        # No usable tab: open a fresh one in the attached context instead of
        # handing out a placeholder page whose frame may detach.
        assert self.context is not None
        fresh = await self.context.new_page()
        self._timeouts(self.context)
        return fresh

    async def fresh_page(self) -> Page:
        """Re-acquire a live page after a detached-frame failure."""
        assert self._browser is not None
        assert self.context is not None
        try:
            fresh = await self.context.new_page()
        except Exception:
            ctxs = self._browser.contexts
            self.context = ctxs[0] if ctxs else await self._browser.new_context()
            fresh = await self.context.new_page()
        self._timeouts(self.context)
        return fresh

    async def _start_attach_auto(self) -> Page:
        assert self._playwright is not None
        self._ensure_debugging()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
        except Exception as error:
            raise RuntimeError(f"Could not attach to open Chrome at {self.cdp_endpoint}: {error}") from error
        ctxs = self._browser.contexts
        self.context = ctxs[0] if ctxs else await self._browser.new_context()
        self._timeouts(self.context)
        return await self._pick_page()
    async def _start_launch(self) -> Page:
        assert self._playwright is not None
        self.profile_path.mkdir(parents=True, exist_ok=True)
        opts: dict = {
            "user_data_dir": str(self.profile_path),
            "headless": False,
        }
        if self.executable_path:
            opts["executable_path"] = str(self.executable_path)
        elif self.browser_channel:
            opts["channel"] = self.browser_channel
        self.context = await self._playwright.chromium.launch_persistent_context(**opts)
        self._timeouts(self.context)
        if self.context.pages:
            return self.context.pages[0]
        return await self.context.new_page()

    async def close(self) -> None:
        # Spec section 5/8: keep browser open whenever manual intervention
        # is required. In attach mode we only disconnect Playwright; the
        # user's real Chrome window/tabs must never be closed.
        try:
            if self.mode == "attach":
                if self._browser is not None:
                    await self._browser.close()
                    # NOTE: for connect_over_cdp, Browser.close() only closes
                    # the CDP connection, not the user's Chrome window.
            elif self.context is not None:
                await self.context.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._browser = None
        self.context = None

