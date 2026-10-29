APP_NAME = "NairaTrader Demo MT5 Worker"
EXNESS_URL = "https://my.exness.com/pa/trading/accounts"
# State signal that the trading-accounts list is on screen (used for
# state-based waits instead of fixed delays).
import re

ACCOUNTS_SIGNAL = re.compile("trading accounts|open account", re.I)
# Default account configuration. The live values come from `.env` via
# config.settings.Settings (NICKNAME, DEMO_DEPOSIT, MAX_LEVERAGE) - these
# constants are only the fallback defaults for a fresh setup.
NICKNAME = "NairaTrader 1.5M"
ACCOUNT_MODE = "DEMO"
ACCOUNT_TYPE = "PRO"
PLATFORM = "MT5"
CURRENCY = "NGN"
DEMO_DEPOSIT = 1_500_000
MAX_LEVERAGE = "1:100"
PASSWORD_PREFIX = "$Manager"
MAX_PASSWORD_DIGITS = 5
# Browser modes: "launch" (Playwright launches Chrome with a dedicated
# profile) or "attach" (connect to your already-open real Chrome over CDP).
BROWSER_MODE = "attach"
BROWSER_CDP_ENDPOINT = "http://127.0.0.1:9222"
BROWSER_CHANNEL = "chrome"

