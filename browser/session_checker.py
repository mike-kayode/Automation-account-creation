import re

from playwright.async_api import Page

from models.enums import SessionStatus


class SessionChecker:
	"""Detects session state from visible page evidence, never from URL alone."""

	def __init__(self, timeout_ms: int):
		self.timeout_ms = timeout_ms

	async def check(self, page: Page) -> SessionStatus:
		body = (await page.locator("body").inner_text()).lower()
		if any(term in body for term in ("captcha", "security challenge", "verify you are", "one-time password")):
			return SessionStatus.MANUAL_ACTION_REQUIRED
		if await self._visible(page.get_by_role("textbox", name=re.compile("email|phone|password", re.I))):
			return SessionStatus.WAITING_FOR_LOGIN
		account_ui = page.get_by_text(re.compile("trading accounts|open account|create account", re.I))
		if await self._visible(account_ui):
			return SessionStatus.AUTHENTICATED
		if any(term in body for term in ("sign in", "log in", "login")):
			return SessionStatus.WAITING_FOR_LOGIN
		return SessionStatus.UNKNOWN

	async def _visible(self, locator) -> bool:
		try:
			return await locator.first.is_visible(timeout=self.timeout_ms)
		except Exception:
			return False
