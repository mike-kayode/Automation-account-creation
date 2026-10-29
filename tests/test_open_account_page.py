"""Account-type picker behaviour, checked against replicas of the real DOM.

Two markup revisions are covered because Exness serves both:

* the CURRENT picker (captured 2026-10-10 from
  https://my.exness.com/pa/new-account?server=demo) is React-Native-Web:
  rows are ``role="radio"`` divs carrying ``data-testid`` hooks and the
  checked state exists ONLY as an inner ``account-row-radio-mark`` node -
  there is no ``aria-checked`` and no ``<input type="radio">`` at all.
* the LEGACY picker used ``data-test`` hooks with a ``Mui-checked`` class.

Before the fix ``validate_account_type`` looked for ``data-test`` hooks and a
Mui class, so it read "nothing is selected" and every job died with
PRO_SELECTION_FAILED right after clicking Pro.
"""

import asyncio
from pathlib import Path

import pytest

from pages.open_account_page import CONTINUE_HOOK, ROW_CONTAINER, OpenAccountPage

ACCOUNT_TYPE_TITLES = ("Standard", "Standard Cent", "Pro", "Raw spread", "Zero")


def _rows(attribute: str, checked_title: str = "Pro", use_mark: bool = True, use_mui: bool = False) -> str:
    rows = []
    for title in ACCOUNT_TYPE_TITLES:
        checked = title == checked_title
        if use_mark:
            radio_inner = f'<div {attribute}="account-row-radio-mark"></div>' if checked else ""
            radio_cls = ""
        else:
            radio_inner = ""
            radio_cls = ' class="Mui-checked"' if checked and use_mui else ""
        rows.append(
            f'<div aria-label="{title}" role="radio" tabindex="0" {attribute}="account-row-container">'
            f"<div>"
            f'<div {attribute}="account-row-title-cell"><div>'
            f'<div {attribute}="account-row-radio"{radio_cls}>{radio_inner}</div>'
            f'<div {attribute}="account-row-title-wrapper">'
            f'<h4 {attribute}="account-row-title">{title}</h4>'
            f"</div></div></div>"
            f"</div></div>"
        )
    return "\n".join(rows)


def _page_html(rows: str) -> str:
    table_attr = "data-testid" if "data-testid" in rows else "data-test"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Open account</title></head>
<body>
<div>Professional accounts</div>
<div {table_attr}="account-types-table">
{rows}
<button role="button" data-testid="account-types-continue" type="button">Continue</button>
</div>
<script>
const rows = document.querySelectorAll('[data-testid="account-row-container"], [data-test="account-row-container"]');
rows.forEach((row) => {{
    row.addEventListener('click', () => {{
        document.querySelectorAll('[data-testid="account-row-radio-mark"], [data-test="account-row-radio-mark"]')
            .forEach((mark) => mark.remove());
        const radio = row.querySelector('[data-testid="account-row-radio"], [data-test="account-row-radio"]');
        const mark = document.createElement('div');
        mark.setAttribute('data-testid', 'account-row-radio-mark');
        radio.appendChild(mark);
    }});
}});
</script>
</body></html>"""


async def _open(tmp_path: Path, html: str):
    """Start a browser and serve `html`; returns (playwright, browser, page)."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = None
    for kwargs in ({"channel": "chrome"}, {}):
        try:
            browser = await playwright.chromium.launch(headless=True, **kwargs)
            break
        except Exception:
            continue
    if browser is None:
        await playwright.stop()
        pytest.skip("no usable browser (need Google Chrome or `playwright install chromium`)")
    page = await browser.new_page()
    target = tmp_path / "picker.html"
    target.write_text(html, encoding="utf-8")
    await page.goto(target.as_uri())
    return playwright, browser, page


async def _close(playwright, browser) -> None:
    await browser.close()
    await playwright.stop()


def test_current_picker_selects_and_validates_pro(tmp_path: Path) -> None:
    async def scenario() -> None:
        playwright, browser, page = await _open(tmp_path, _page_html(_rows("data-testid")))
        try:
            form = OpenAccountPage(page, timeout_ms=4000, poll_ms=40, retries=10)
            assert await page.locator(ROW_CONTAINER).count() == len(ACCOUNT_TYPE_TITLES)
            # Pro arrives pre-checked, as in the user's screenshot.
            assert await form.validate_account_type() is True
            assert await form.is_pro_selected() is True
            # Full select_pro(): wait -> click the row -> verify selection.
            await form.select_pro()
            assert await form.validate_account_type() is True
            # The Continue control resolves through its stable hook.
            assert await page.locator(CONTINUE_HOOK).count() == 1
            # Picking a different account type must fail validation, and
            # re-selecting Pro must recover - validation tracks live state.
            await page.get_by_role("radio", name="Standard", exact=True).click()
            assert await form.validate_account_type() is False
            assert await form.is_pro_selected() is False
            await form.select_pro()
            assert await form.validate_account_type() is True
        finally:
            await _close(playwright, browser)

    asyncio.run(scenario())


def test_legacy_data_test_markup_still_validates(tmp_path: Path) -> None:
    async def scenario() -> None:
        rows = _rows("data-test", use_mark=False, use_mui=True)
        playwright, browser, page = await _open(tmp_path, _page_html(rows))
        try:
            form = OpenAccountPage(page, timeout_ms=4000, poll_ms=40, retries=10)
            assert await form.validate_account_type() is True
            assert await form.is_pro_selected() is True
            await form.select_pro()
            assert await form.validate_account_type() is True
        finally:
            await _close(playwright, browser)

    asyncio.run(scenario())


def test_picker_rejects_when_standard_is_the_checked_row(tmp_path: Path) -> None:
    async def scenario() -> None:
        html = _page_html(_rows("data-testid", checked_title="Standard"))
        playwright, browser, page = await _open(tmp_path, html)
        try:
            form = OpenAccountPage(page, timeout_ms=4000, poll_ms=40, retries=10)
            assert await form.validate_account_type() is False
            assert await form.is_pro_selected() is False
        finally:
            await _close(playwright, browser)

    asyncio.run(scenario())
