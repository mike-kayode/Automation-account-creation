from playwright.async_api import Page

from config.constants import ACCOUNTS_SIGNAL


async def _goto_resilient(page: Page, url: str, timeout_ms: int = 30000) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception as error:
        if "detached" not in str(error).lower():
            raise
        # The attached tab's frame died (e.g. a chrome:// placeholder or a
        # tab the user closed). Ask the caller to swap pages via fresh_page().
        raise


def _on_accounts_list(page: Page) -> bool:
    # SPA URL is authoritative for the current route - safe and instant.
    url = (page.url or "").lower()
    return "my.exness.com/pa/trading/accounts" in url


async def open_accounts_page(page: Page, url: str, timeout_ms: int = 30000) -> None:
    # Speed rule: do not reload the Personal Area unless we are actually
    # off the accounts list. Reuse the same page/session whenever possible;
    # every wait below is state-based (wait for the list signal), never fixed.
    if _on_accounts_list(page):
        try:
            await ACCOUNTS_SIGNAL_PATTERN(page).first.wait_for(state="visible", timeout=3000)
            return
        except Exception:
            pass  # URL matches but list not rendered - fall through to reload.
    await _goto_resilient(page, url, timeout_ms)
    try:
        await ACCOUNTS_SIGNAL_PATTERN(page).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass


def ACCOUNTS_SIGNAL_PATTERN(page: Page):
    return page.get_by_text(ACCOUNTS_SIGNAL)
