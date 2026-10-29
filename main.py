import asyncio
import sys

from cryptography.fernet import Fernet
from rich.console import Console
from rich.panel import Panel

from browser.browser_manager import BrowserManager
from browser.navigation import open_accounts_page
from config.settings import Settings
from database.connection import Database
from database.repositories.event_repository import EventRepository
from services.logging_service import configure_logging
from worker.worker_manager import WorkerManager


async def async_main() -> int:
    console = Console()
    database = None
    browser = None
    try:
        settings = Settings.from_env()
        if not settings.encryption_key and not settings.test_mode:
            raise ValueError("ENCRYPTION_KEY is required; set it in .env before starting the worker")
        if not settings.encryption_key:
            settings.encryption_key = Fernet.generate_key().decode("ascii")
        database = Database(settings.database_path)
        database.initialize()
        logger = configure_logging("logs")
        EventRepository(database).log_event("APPLICATION_STARTED")
        EventRepository(database).log_event("DATABASE_INITIALIZED")
        if settings.browser_mode == "attach":
            browser_desc = f"ATTACHED REAL CHROME ({settings.browser_cdp_endpoint}) - your own logged-in window"
        else:
            browser_desc = f"VISIBLE GOOGLE CHROME ({settings.browser_channel})"
        console.print(Panel.fit(
            f"[bold]NAIRATRADER DEMO MT5 WORKER[/bold]\n\n"
            f"Account Type: {settings.account_type}\n"
            f"Account Mode: {settings.account_mode}\n"
            f"Platform: {settings.platform}\n"
            f"Nickname: {settings.nickname}\n"
            f"Currency: {settings.currency}\n"
            f"Deposit: {settings.demo_deposit:,}\n"
            f"Leverage: {settings.max_leverage}\n\n"
            f"Browser: {browser_desc}\n"
            f"Test mode: {settings.test_mode}",
            title=settings.app_name,
        ))
        browser = BrowserManager(
            settings.browser_profile_path,
            settings.navigation_timeout_ms,
            settings.browser_channel,
            settings.browser_executable_path,
            settings.browser_mode,
            settings.browser_cdp_endpoint,
        )
        page = await browser.start()
        EventRepository(database).log_event("BROWSER_STARTED")
        if settings.browser_mode == "attach":
            console.print(
                "[green]Attached to your real Chrome. Using your current tab/session - "
                "it will NOT be closed.[/green]"
            )
            # Do not force navigation: reuse the already-logged-in Exness tab.
            # Open the accounts page only if we are not already on Exness.
            try:
                current_url = (page.url or "").lower()
            except Exception:
                current_url = ""
            if "exness.com" not in current_url:
                try:
                    await open_accounts_page(page, settings.exness_url)
                except Exception as error:
                    # The attached tab's frame detached (stale chrome://
                    # placeholder or user-closed tab). Open a fresh tab in the
                    # same attached context and continue - never crash here.
                    if "detached" in str(error).lower():
                        console.print("[yellow]Attached tab was stale; opening a fresh tab...[/yellow]")
                        page = await browser.fresh_page()
                        await open_accounts_page(page, settings.exness_url)
                    else:
                        raise
        else:
            await open_accounts_page(page, settings.exness_url)
        EventRepository(database).log_event("PAGE_OPENED")
        manager = WorkerManager(database, settings, console, logger)
        await manager.wait_for_authentication(page)
        await manager.recover_unfinished(page)
        count_text = await asyncio.to_thread(input, "Enter number of accounts: ")
        count = int(count_text)
        if count <= 0:
            raise ValueError("number of accounts must be greater than zero")
        await manager.run_batch(page, count)
        return 0
    except KeyboardInterrupt:
        console.print("[yellow]Shutdown requested. Current persisted state was left unchanged.[/yellow]")
        return 130
    except Exception as error:
        Console(stderr=True).print(f"[red]WORKER_ERROR[/red]: {error}")
        return 1
    finally:
        if browser is not None:
            await browser.close()
        if database is not None:
            database.close()


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
