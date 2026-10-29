# One-Account Creation Design

## Scope

Process one demo MT5 Pro account through the visible Exness UI after the operator has manually authenticated. The worker must stop for manual review when the UI, session, or result is uncertain.

## Pseudocode

```text
START
  load and validate configuration
  initialize SQLite and event logging
  connect to the operator's visible Chrome session
  open or reuse the Exness trading accounts page
  wait until the operator session is authenticated

  create one batch with one pending job
  claim the job
  capture the current account-number set as BASELINE

  click Open account
  wait for account-type page
  scroll Pro option into view
  select Pro
  verify Pro is selected and every other account type is unselected
  scroll Continue into view
  click Continue once

  wait for account setup page
  verify Demo is selected; stop if Real is selected
  select NGN and verify NGN
  enter the configured DEMO_DEPOSIT (any positive amount from `.env`) and verify the numeric value
  enter the configured NICKNAME (any nickname from `.env`) and read it back
  select the configured MAX_LEVERAGE (e.g. 1:50, 1:100, 1:500 from `.env`) and verify it
  select MT5 and verify MT5
    generate "$Manager" plus exactly five random digits using `secrets`
  encrypt and persist the password before submission
  enter the password

  scroll through the form as needed
  validate all required values
  persist READY_TO_SUBMIT

  if TEST_MODE:
      persist PAUSED and do not click Create account
      STOP

  persist SUBMITTING
  click Create account exactly once
  do not retry if the result is uncertain

  capture the post-submit account set
  reconcile AFTER minus BASELINE
  if exactly one new account:
      extract MT5 number from visible account data
      append MT5 number + the exact current-job password to report/accounts.csv
      flush, reopen, and verify the exact row
      persist verified account and SUCCESS
      only then start the next job
  otherwise:
      capture screenshot
      persist MANUAL_REVIEW
END
```

## Components

- `BrowserManager`: attaches to the operator's Chrome CDP endpoint or launches a dedicated visible Chrome profile.
- `AccountsPage`: waits for account list, selects Demo, opens account creation, and captures account identifiers.
- `OpenAccountPage`: owns only form interaction. Every control is located by accessible label/role/text, scrolled into view, acted on, and verified.
- `JobProcessor`: persists state around each step, encrypts the password before submission, and permits only one final submission click.
- `Reconciler`: accepts success only when exactly one new account identifier appears.
- SQLite repositories: authoritative state, events, and encrypted job password.

## Scroll and selector policy

1. Prefer accessible role/name and labels.
2. Use visible text and stable DOM relationships next.
3. Call `scroll_into_view_if_needed()` before interacting with controls below the viewport.
4. Never use coordinates, screenshots, generated CSS classes, or `nth-child()`.
5. If a control cannot be uniquely located or verified, stop rather than guess.

## Failure policy

- CAPTCHA, MFA, identity verification, or security challenge: pause for manual action.
- Missing or changed UI element before submission: fail the job without submitting.
- Error after submission or uncertain browser state: manual review and reconciliation; never resubmit.
- Zero or multiple new accounts after submission: manual review.

## PASSWORD GENERATION MUST NOT BE FORGOTTEN

For every account, the password is `$Manager` followed by exactly five digits generated with Python `secrets`. Generate it once, store it for the current job, use it during account creation, and write that exact value to the report. Never regenerate or replace it while reporting.

## Mandatory account report gate

For every job, capture the current account-card numbers as `before_accounts` before opening the form and generate one password in the form `$Manager` plus exactly five random digits. Keep that password associated with the job and use the same value in the form and report.

After creation, return to the trading-account list and capture the account-card numbers again. The new MT5 account is the unique number in `after_accounts - before_accounts`; never select by position, expansion state, or a previously stored number. If there is no unique number, or the job password is unavailable, stop at `MANUAL_REVIEW` without writing a record.

Append the triple to `report/accounts.csv` with the header `MT5 Number,Password,Nickname`. Flush the file, reopen it, and confirm the new MT5 number, its exact password, and the configured nickname occur on the same row. Retry a failed write before manual review. Do not start another account until this verification succeeds and the job is `SUCCESS`.
