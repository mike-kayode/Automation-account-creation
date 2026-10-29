import re

from playwright.async_api import Page


class AccountDetailsPage:
    def __init__(self, page: Page):
        self.page = page

    async def get_mt5_number(self) -> str:
        # Prefer the stable card hook over body-text regex (the footer
        # contains lookalike numbers like the Seychelles reg number).
        try:
            card = self.page.locator(
                '[data-test="account-card"][data-account-number], [data-testid="account-card"][data-account-number]'
            ).first
            await card.wait_for(state="attached", timeout=1500)
            number = await card.get_attribute("data-account-number")
            if number and re.fullmatch(r"\d{7,12}", number):
                return number
        except Exception:
            pass
        text = await self.page.locator("body").inner_text()
        matches = re.findall(r"(?<!\d)\d{7,12}(?!\d)", text)
        if not matches:
            raise LookupError("MT5_NUMBER_NOT_FOUND")
        return matches[0]

    async def _value_near(self, label: str) -> str | None:
        locator = self.page.get_by_text(re.compile(f"^{re.escape(label)}$", re.I)).first
        if not await locator.count():
            return None
        parent = locator.locator("..")
        return (await parent.inner_text()).strip()

    async def get_account_type(self) -> str | None:
        return await self._value_near("Account type")

    async def get_platform(self) -> str | None:
        return await self._value_near("Platform")

    async def get_currency(self) -> str | None:
        return await self._value_near("Currency")

    async def get_nickname(self) -> str | None:
        return await self._value_near("Nickname")

    async def get_server(self, mt5_number: str | None = None, timeout_ms: int = 20000) -> str | None:
        # Server is NOT rendered on the list page (verified in captured DOM).
        # Open the account card's settings and read it there, else fall back
        # to any Exness-MT5Trial/Real string on the page (post-create dialog).
        if mt5_number:
            card = self.page.locator(
                f'[data-test="account-card"][data-account-number="{mt5_number}"], '
                f'[data-testid="account-card"][data-account-number="{mt5_number}"]'
            ).first
            try:
                await card.wait_for(state="visible", timeout=timeout_ms)
                # The data-test hook can sit on the button itself or on a
                # wrapper. Never blind-click the first button in the card
                # (it may be the Trade button, opening an unrelated modal).
                for opener in (
                    card.locator('button[data-test="account-cog-menu-desktop"], button[data-testid="account-cog-menu-desktop"]').first,
                    card.locator('[data-test="account-cog-menu-desktop"] button, [data-testid="account-cog-menu-desktop"] button').first,
                    card.locator('button[data-test="account-cog-menu-mobile"], button[data-testid="account-cog-menu-mobile"]').first,
                ):
                    try:
                        if not await opener.count() or not await opener.is_visible():
                            continue
                        await opener.scroll_into_view_if_needed(timeout=1500)
                        await opener.click(timeout=2500)
                        break
                    except Exception:
                        continue
                # State-based wait (no fixed 1s sleeps): poll the DOM inside
                # the browser every 200ms until the server string appears,
                # bounded by timeout_ms. Returns the instant it is found.
                poll_ms = 200
                try:
                    await self.page.wait_for_function(
                        """(args) => {
                            const body = document.body ? document.body.innerText : '';
                            if (/Exness-MT5(?:Trial|Real)\\d*/.test(body)) return true;
                            const labels = [...document.querySelectorAll('*')]
                                .filter((el) => el.children.length === 0 &&
                                    /^server$/i.test((el.textContent || '').trim()));
                            return labels.some((el) =>
                                /exness/i.test((el.parentElement ? el.parentElement.innerText : '') || ''));
                        }""",
                        timeout=timeout_ms,
                        polling=poll_ms,
                    )
                except Exception:
                    pass
                # Close the opened menu regardless of outcome so the next
                # scan of the accounts list starts from a clean UI state.
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass
                try:
                    body = await self.page.locator("body").inner_text()
                except Exception:
                    body = ""
                match = re.search(r"Exness-MT5(?:Trial|Real)\d*", body)
                if match:
                    return match.group(0)
                server = await self._value_near("Server")
                if server and "exness" in server.lower():
                    return server.strip()
            except Exception:
                pass
        try:
            body = await self.page.locator("body").inner_text()
        except Exception:
            return None
        match = re.search(r"Exness-MT5(?:Trial|Real)\d*", body)
        if match:
            return match.group(0)
        return await self._value_near("Server")
