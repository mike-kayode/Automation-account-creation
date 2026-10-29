"""Check attach to already-open Chrome. Run: python tools/check_attach.py"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import Settings
from browser.browser_manager import BrowserManager


async def main() -> int:
    s = Settings.from_env()
    print(f"mode={s.browser_mode} cdp={s.browser_cdp_endpoint}")
    m = BrowserManager(s.browser_profile_path, s.navigation_timeout_ms,
                       s.browser_channel, s.browser_executable_path,
                       s.browser_mode, s.browser_cdp_endpoint)
    page = await m.start()
    print(f"ATTACHED OK url={page.url}")
    print("Your already-open Exness tab is now under worker control.")
    print("Worker did NOT close anything. Press Enter to disconnect...")
    try:
        await asyncio.to_thread(input)
    except Exception:
        pass
    await m.close()
    print("Disconnected, Chrome still open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

