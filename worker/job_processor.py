import json
import logging

from playwright.async_api import Page

from browser.navigation import open_accounts_page
from config.settings import Settings
from database.connection import Database
from database.repositories.account_repository import AccountRepository
from database.repositories.event_repository import EventRepository
from database.repositories.job_repository import JobRepository
from models.account import CreatedAccount
from models.enums import JobStatus
from pages.account_details_page import AccountDetailsPage
from pages.accounts_page import AccountsPage
from pages.open_account_page import OpenAccountPage
from services.encryption_service import EncryptionService
from services.csv_service import save_account_and_verify
from services.password_service import PasswordService
from services.screenshot_service import capture, capture_dom_state
from worker.reconciler import reconcile


class JobProcessor:
	def __init__(self, database: Database, settings: Settings, logger: logging.Logger):
		self.database = database
		self.settings = settings
		self.logger = logger
		self.jobs = JobRepository(database)
		self.accounts = AccountRepository(database)
		self.events = EventRepository(database)
		self.passwords = PasswordService(settings.password_prefix, settings.max_password_digits)
		if not settings.encryption_key:
			raise ValueError("ENCRYPTION_KEY is required before processing jobs")
		self.encryption = EncryptionService(settings.encryption_key)

	async def process(self, page: Page, job_id: str) -> JobStatus:
		submitted = False
		accounts_page = AccountsPage(page, self.settings.element_timeout_ms)
		try:
			await self._transition(job_id, JobStatus.PRECHECK, "PRECHECK")
			# Recovery invariant: every job (re)starts from the accounts list.
			# After MANUAL_REVIEW the browser is left on the account-type page,
			# so navigate back first - otherwise select_demo/open_new_account
			# time out waiting for list-page controls (the crash-loop cause).
			# Rule 3/6: reuse the current page - only navigate when we are
			# NOT already on the accounts list (e.g. after MANUAL_REVIEW the
			# browser sits on the form). Skip the reload when the previous
			# job already left us on the list.
			if "my.exness.com/pa/trading/accounts" not in (page.url or "").lower():
				await open_accounts_page(page, self.settings.exness_url)
			await accounts_page.wait_until_loaded()
			# Spec section 3: capture existing account IDs first.
			baseline = await accounts_page.get_account_identifiers()
			self.jobs.set_baseline(job_id, json.dumps(sorted(baseline)))
			await self._transition(job_id, JobStatus.BASELINE_CAPTURED, "BASELINE_CAPTURED")
			# STEP 2: generate the password exactly once, right after the
			# baseline capture. It is persisted now and never regenerated
			# for this job.
			password = self.passwords.generate()
			self.jobs.set_password(job_id, self.encryption.encrypt(password))

			await accounts_page.open_new_account()
			await self._transition(job_id, JobStatus.OPENING_FORM, "OPEN_ACCOUNT_PAGE")
			form = OpenAccountPage(
				page,
				self.settings.element_timeout_ms,
				poll_ms=self.settings.verify_poll_ms,
				retries=self.settings.verify_retries,
			)
			# Spec section 3/5 order: Open Account -> Select PRO (+verify)
			# -> Select DEMO -> Select MT5 -> Configure -> Validate -> Submit once.
			try:
				await form.select_pro()
			except (LookupError, ValueError) as error:
				return await self._manual_review(page, job_id, "PRO_SELECTION_FAILED", str(error))
			# select_pro() already verified PRO is the checked row - skip the
			# duplicate full-row validation scan (speed rule 7).
			await self._transition(job_id, JobStatus.CONFIGURING, "ACCOUNT_TYPE_SELECTED")
			await form.click_continue()

			await form.configure_demo()
			await form.configure_mt5()
			await form.configure_nickname(self.settings.nickname)
			await form.configure_currency(self.settings.currency)
			await form.configure_deposit(self.settings.demo_deposit)
			await form.configure_leverage(self.settings.max_leverage)
			await form.configure_password(password)
			await self._transition(job_id, JobStatus.VALIDATING, "ACCOUNT_CONFIGURATION_VALIDATED")
			validation = await form.validate_configuration(
				self.settings.nickname, self.settings.currency, self.settings.demo_deposit,
				password, self.settings.max_leverage,
			)
			if not all(validation.values()):
				failed = sorted(name for name, ok in validation.items() if not ok)
				return await self._manual_review(
					page, job_id, "FORM_VALIDATION_FAILED", f"invalid fields: {', '.join(failed)}"
				)
			await self._transition(job_id, JobStatus.READY_TO_SUBMIT, "READY_TO_SUBMIT")
			if self.settings.test_mode:
				self.events.log_event("TEST_MODE_SUBMISSION_DISABLED", job_id=job_id)
				self.jobs.save_error(job_id, "TEST_MODE", "Final submission disabled by TEST_MODE", JobStatus.PAUSED)
				return JobStatus.PAUSED

			# Spec section 6: submit exactly once, only after every field verified.
			await self._transition(job_id, JobStatus.SUBMITTING, "SUBMISSION_STARTED")
			submitted = True
			await form.submit()
			await self._transition(job_id, JobStatus.VERIFYING, "SUBMISSION_FINISHED")
			# Spec section 6: if submission status is uncertain, DO NOT CLICK
			# AGAIN. STEP 9: state-based wait - block until the account list
			# shows an account number that is NOT in the baseline (bounded by
			# navigation_timeout_ms), then diff immediately. No fixed sleeps.
			after = await self._wait_for_new_account(page, accounts_page, baseline)
			await self._transition(job_id, JobStatus.RECONCILING, "RECONCILIATION_STARTED")
			result = reconcile(baseline, after)
			if result.requires_manual_review or result.candidate is None:
				return await self._manual_review(page, job_id, result.reason or "ACCOUNT_RECONCILIATION_FAILED")
			# STEP 11: the report needs ONLY MT5 + password. Write and
			# verify it IMMEDIATELY after detecting the new account -
			# before any optional metadata collection.
			mt5_number = result.candidate
			password_encrypted = self.jobs.get(job_id)["password_encrypted"]
			path = None
			report_error = None
			for _ in range(3):
				try:
					path = save_account_and_verify(mt5_number, password, self.settings.nickname, self.settings.export_directory)
					report_error = None
					break
				except (OSError, ValueError) as error:
					report_error = error
			if report_error is not None or path is None:
				return await self._manual_review(page, job_id, "REPORT_WRITE_FAILED", str(report_error))
			self.events.log_event("REPORT_VERIFIED", job_id=job_id, message=str(path))
			# Server is OPTIONAL DB metadata only (never in the CSV report
			# and not rendered on the list page). Short bounded best-effort
			# attempt that can NEVER fail an already-verified report.
			server = None
			try:
				server = await AccountDetailsPage(page).get_server(mt5_number, timeout_ms=2500)
			except Exception:
				server = None
			if not server:
				self.events.log_event(
					"SERVER_NOT_DETECTED", level="WARNING", job_id=job_id,
					message="Server string not shown; report already verified",
				)
			account = CreatedAccount(
				job_id=job_id, mt5_number=mt5_number,
				password_encrypted=password_encrypted,
				nickname=self.settings.nickname, account_mode=self.settings.account_mode,
				account_type=self.settings.account_type, platform=self.settings.platform,
				currency=self.settings.currency, demo_deposit=self.settings.demo_deposit,
				server=server, created_at="",
			)
			self.accounts.create_verified_account(account)
			await self._transition(job_id, JobStatus.SUCCESS, "ACCOUNT_VERIFIED")
			return JobStatus.SUCCESS
		except Exception as error:
			# Spec section 8: never crash the whole batch for one page/selector
			# failure. Pre-submit selector/state failures go to MANUAL_REVIEW
			# (browser stays open); post-submit uncertainty also MANUAL_REVIEW.
			if submitted:
				return await self._manual_review(page, job_id, "SUBMISSION_UNCERTAIN", str(error))
			if isinstance(error, (LookupError, ValueError)):
				return await self._manual_review(page, job_id, "EXPECTED_ELEMENT_NOT_FOUND", str(error))
			self.jobs.save_error(job_id, "EXPECTED_ELEMENT_NOT_FOUND", str(error), JobStatus.FAILED)
			self.events.log_event("JOB_FAILED", level="ERROR", job_id=job_id, message=str(error))
			return JobStatus.FAILED

	async def _wait_for_new_account(self, page: Page, accounts_page: AccountsPage, baseline: set[str]) -> set[str]:
		# STEP 9/10: wait for the real Exness post-create state - an account
		# card (or on-page number) whose MT5 number is absent from the
		# baseline. Pure state-based waiting: returns the moment a new
		# account is detectable; bounded by navigation_timeout_ms only as a
		# failure limit, never a fixed delay.
		await accounts_page.wait_until_loaded()
		try:
			current = await accounts_page.get_account_identifiers()
			if current - baseline:
				return current
		except Exception:
			pass
		try:
			await page.wait_for_function(
				"""(baseline) => {
					const seen = [];
					document.querySelectorAll('[data-account-number]').forEach((card) => {
						const number = card.getAttribute('data-account-number');
						if (number) seen.push(number);
					});
					const text = document.body ? document.body.innerText : '';
					for (const match of text.matchAll(/(?<!\\d)\\d{7,12}(?!\\d)/g)) seen.push(match[0]);
					return seen.some((number) => !baseline.includes(number));
				}""",
				arg=sorted(baseline),
				timeout=self.settings.navigation_timeout_ms,
				polling=self.settings.verify_poll_ms,
			)
		except Exception:
			pass  # Bounded wait expired: the final read + reconcile decides.
		return await accounts_page.get_account_identifiers()

	async def _transition(self, job_id: str, status: JobStatus, event: str) -> None:
		self.jobs.update_status(job_id, status)
		self.events.log_event(event, job_id=job_id)

	async def _manual_review(self, page: Page, job_id: str, code: str, message: str | None = None) -> JobStatus:
		# Spec section 5/8: PAUSE -> screenshot -> log DOM/state -> keep
		# browser open -> request manual intervention. Never terminate worker.
		# Spec section 9: passwords must never appear in logs or screenshots
		# (capture() masks password inputs before screenshotting).
		safe_message = self._redact(message or code)
		try:
			await capture(page, self.settings.screenshot_directory, f"job-{job_id}-manual-review")
		except Exception as capture_error:
			self.events.log_event("SCREENSHOT_FAILED", level="WARNING", job_id=job_id, message=str(capture_error))
		try:
			dom_path = await capture_dom_state(page, self.settings.screenshot_directory, f"job-{job_id}-manual-review")
		except Exception:
			dom_path = None
		try:
			current_url = page.url
		except Exception:
			current_url = "<unknown>"
		self.jobs.save_error(job_id, code, safe_message, JobStatus.MANUAL_REVIEW)
		self.events.log_event(
			"MANUAL_REVIEW_REQUIRED", level="WARNING", job_id=job_id, message=safe_message,
			metadata={"code": code, "url": current_url, "dom": str(dom_path) if dom_path else None},
		)
		return JobStatus.MANUAL_REVIEW

	@staticmethod
	def _redact(text: str) -> str:
		import re
		return re.sub(r"\$(?:Trader|Manager)\d{5}", "$Manager*****", text)
