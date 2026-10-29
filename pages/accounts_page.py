import re

from playwright.async_api import Page

from config.constants import ACCOUNTS_SIGNAL


class AccountsPage:
    def __init__(self, page: Page, timeout_ms: int = 15000):
        self.page = page
        self.timeout_ms = timeout_ms

    async def wait_until_loaded(self) -> None:
        await self.page.get_by_text(ACCOUNTS_SIGNAL).first.wait_for(
            state="visible", timeout=self.timeout_ms
        )

    async def get_account_identifiers(self) -> set[str]:
        await self.wait_until_loaded()
        cards = self.page.locator(
            '[data-test="account-card"][data-account-number], [data-testid="account-card"][data-account-number]'
        )
        card_numbers = set()
        for index in range(await cards.count()):
            number = await cards.nth(index).get_attribute("data-account-number")
            if number and re.fullmatch(r"\d{7,12}", number):
                card_numbers.add(number)
        text = await self.page.locator("body").inner_text()
        visible_numbers = set(re.findall(r"(?<!\d)\d{7,12}(?!\d)", text))
        return card_numbers | visible_numbers

    async def open_new_account(self) -> None:
        # WAIT -> DETECT -> ACTION -> VERIFY -> CONTINUE.
        # Caller guarantees we start on the accounts list; do NOT touch the
        # Demo tab here (it does not exist on the account-type page, and
        # waiting for it there caused the 15s-timeout crash loop).
        await self.wait_until_loaded()
        candidates = [
            self.page.get_by_role(
                "button",
                name=re.compile("open account|new account|create account", re.I),
            ),
            self.page.get_by_text(re.compile("^open account$|^new account$", re.I)),
        ]
        for candidate in candidates:
            try:
                await candidate.first.wait_for(
                    state="visible", timeout=self.timeout_ms
                )
            except Exception:
                continue
            await candidate.first.scroll_into_view_if_needed()
            try:
                enabled = await candidate.first.is_enabled(timeout=2000)
            except Exception:
                enabled = True
            if not enabled:
                continue
            await candidate.first.click()
            # VERIFY: account-type page must appear before continuing.
            try:
                await self.page.get_by_text(
                    re.compile("set up your account|professional accounts", re.I)
                ).first.wait_for(state="visible", timeout=self.timeout_ms)
            except Exception:
                continue
            return
        raise LookupError("EXPECTED_ELEMENT_NOT_FOUND: open account control")

    async def select_demo(self) -> None:
        candidates = [
            self.page.get_by_role("tab", name=re.compile("^Demo$", re.I)),
            self.page.get_by_text("Demo", exact=True),
        ]
        for candidate in candidates:
            try:
                await candidate.first.wait_for(
                    state="visible", timeout=self.timeout_ms
                )
            except Exception:
                continue
            await candidate.first.scroll_into_view_if_needed()
            await candidate.first.click()
            return
        raise LookupError("EXPECTED_ELEMENT_NOT_FOUND: Demo account tab")
