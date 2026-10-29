"""Dump Open Account DOM for selector fix. Run: python tools/inspect_open_account.py"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from browser.browser_manager import BrowserManager


async def main() -> int:
    s = Settings.from_env()
    m = BrowserManager(s.browser_profile_path, s.navigation_timeout_ms,
                       s.browser_channel, s.browser_executable_path,
                       s.browser_mode, s.browser_cdp_endpoint)
    page = await m.start()
    print(f"URL={page.url}")
    # Make sure we are on open-account page
    if "open" not in (page.url or "").lower():
        print("Not on open-account page. Current URL above - navigating to Exness accounts.")
        await page.goto(s.exness_url)
        print("Go to Open account manually in the window, then press Enter here...")
        await asyncio.to_thread(input)
    html = await page.content()
    out = Path("logs/open_account.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Saved {out} len={len(html)}")
    # Print focused snippet around Professional accounts
    idx = html.lower().find("professional accounts")
    print(html[max(0, idx-2000):idx+8000][:10000])
    # Probe locators
    radios = page.get_by_role("radio")
    print(f"radio count={await radios.count()}")
    for name in ["Pro", "Standard", "Raw spread", "Zero"]:
        try:
            loc = page.get_by_role("radio", name=name)
            print(f"radio[{name}] count={await loc.count()}")
        except Exception as e:
            print(f"radio[{name}] err {e}")
    # inputs
    print("input[type=radio] count=", await page.locator('input[type="radio"]').count())
    try:
        n = await page.locator('input[type="radio"]').count()
        for i in range(min(n, 8)):
            el = page.locator('input[type="radio"]').nth(i)
            try:
                val = await el.evaluate("e => ({checked: e.checked, name: e.name, value: e.value, outer: e.outerHTML.slice(0,300)})")
                print(i, val)
            except Exception as e:
                print(i, "err", e)
    except Exception as e:
        print("inputs err", e)
    # card containers containing Pro text
    try:
        cards = page.locator("div:has-text('Professional accounts') ~ div, div:has(> div:text('Pro'))")
        print("cards probe done")
    except Exception as e:
        print(e)
    await m.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
