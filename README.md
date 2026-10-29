# NairaTrader Demo MT5 Account Worker

A local-only Python worker for creating demo MT5 accounts through a visible, manually authenticated Exness browser session. It uses SQLite as the source of truth and Fernet encryption for stored passwords.

## Safety boundary

The eventual worker is designed for a visible, manually authenticated browser session. It must not bypass CAPTCHA, MFA, security challenges, or bot detection. It must stop for manual review when external state is uncertain. No credentials are hard-coded, and passwords are never written to normal logs.

## Requirements

- Windows 10/11
- Python 3.12 or newer
- PowerShell
- Real Google Chrome installed (the worker attaches to it, no Playwright browser download needed in attach mode)

## Installation

```powershell
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Set `ENCRYPTION_KEY` to a locally generated Fernet key when using encrypted job data:

```powershell
py -c "from services.encryption_service import EncryptionService; print(EncryptionService.generate_key())"
```

Keep the key private and never commit `.env`.

## Account configuration

These three `.env` keys control how the created demo accounts look and can be
changed freely - everything else (`ACCOUNT_MODE=DEMO`, `ACCOUNT_TYPE=PRO`,
`PLATFORM=MT5`, `CURRENCY=NGN`, `$Manager` + 5 digits password) stays fixed:

```dotenv
# Any nickname for the accounts
NICKNAME=NairaTrader 1.5M
# Account size - any positive amount in NGN
DEMO_DEPOSIT=1500000
# Leverage - any option the Exness form offers, e.g. 1:50, 1:100, 1:500,
# 1:1000, 1:2000 or 1:Unlimited
MAX_LEVERAGE=1:100
```

The startup panel echoes the active values before any browser work starts, and
invalid values (blank nickname, non-positive deposit, malformed leverage) fail
fast at startup instead of halfway through a batch.

## Run (real original Chrome - recommended)

Google blocks sign-in from automation-branded Chromium windows with
"This browser or app may not be secure". To avoid that, the worker now
attaches to your **real original Chrome app** instead of opening its own
Chromium tab:

```powershell
# Terminal 1: open your REAL Chrome with debugging enabled (keep it open)
powershell -ExecutionPolicy Bypass -File tools/launch_chrome_debug.ps1

# In that Chrome window: log in to Google + Exness manually
# (your existing logged-in tab keeps working - nothing is closed).

# Terminal 2: attach the worker to that open Chrome window
py main.py
```

`BROWSER_MODE=attach` (default in `.env`) connects to
`BROWSER_CDP_ENDPOINT=http://127.0.0.1:9222` and reuses whichever tab is
already on Exness, so it never forces a fresh login. Closing the worker only
disconnects - it never closes your real browser.

Fallback (old behaviour, more likely to hit the Google block):

```powershell
# set BROWSER_MODE=launch in .env, then:
py main.py
```

The worker validates the fixed workflow configuration, opens the Exness trading accounts page, and waits for manual login. It never enters credentials or interacts with CAPTCHA, MFA, or security challenges.

`TEST_MODE=true` is the default and prevents the final account-creation click after form validation. Set `TEST_MODE=false` only after inspecting the live DOM and completing controlled testing. Live mode requires a valid local `ENCRYPTION_KEY`.

## Tests

```powershell
py -m pytest -q
```

The tests cover exact workflow configuration, `$Manager` plus five digits password generation, Fernet round trips, SQLite foreign keys, transactions, job claiming, verified-account persistence, state transitions, and zero/one/multiple-account reconciliation.

## Local data

- `database/worker.db` is the authoritative SQLite source and is ignored by Git.
- `report/accounts.csv` is the append-only completed-account report and is ignored by Git. `screenshots/` is reserved for manual-review captures and is ignored by Git.
- `browser_profile/` and `logs/` are reserved for later phases and are ignored by Git.

The database tables are `batches`, `jobs`, `created_accounts`, and `events`. A created account is inserted only after external account-list reconciliation finds exactly one new MT5 identifier. Submission errors are treated as uncertain and become `MANUAL_REVIEW`; the worker never automatically clicks Create again.

## Browser setup

Attach mode (default): no Playwright browser download needed - it uses your installed Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe` via `tools/launch_chrome_debug.ps1`.

Launch mode fallback: install the browser Playwright launches with:

```powershell
py -m playwright install chromium
```

In launch mode the browser profile is stored locally under `browser_profile/google-chrome/` and is ignored by Git. This is a dedicated automation profile, separate from your everyday Chrome profile. Login must be completed manually in the visible browser. If the page shows a security challenge, the worker pauses for manual action.

## Recovery and exports

On startup, interrupted jobs are compared with their saved baseline. Exactly one new account can be recovered; zero or multiple candidates require manual review. After each creation, the new MT5 number is paired with the exact `$Manager` password generated for that job and appended to `report/accounts.csv`; the file is reopened and verified before the job becomes `SUCCESS` or the next account starts. Missing accounts, missing passwords, or failed report verification stop the batch for manual review.
