import asyncio
import json
import logging

from playwright.async_api import Page
from rich.console import Console

from browser.navigation import open_accounts_page
from browser.session_checker import SessionChecker
from config.settings import Settings
from database.connection import Database
from database.repositories.batch_repository import BatchRepository
from database.repositories.account_repository import AccountRepository
from database.repositories.event_repository import EventRepository
from database.repositories.job_repository import JobRepository
from models.account import CreatedAccount
from models.enums import BatchStatus, JobStatus, SessionStatus
from pages.account_details_page import AccountDetailsPage
from services.csv_service import save_account_and_verify
from services.encryption_service import EncryptionService
from worker.job_processor import JobProcessor
from worker.reconciler import reconcile


# Error codes that prove the account was submitted on Exness: the account
# EXISTS even though its report row was never written (the old server-string
# gate failed the job AFTER account creation).
SUBMITTED_ERROR_CODES = (
    "SUCCESS_CRITERIA_UNMET",
    "REPORT_WRITE_FAILED",
    "SUBMISSION_UNCERTAIN",
)


class WorkerManager:
	def __init__(self, database: Database, settings: Settings, console: Console, logger: logging.Logger):
		self.database = database
		self.settings = settings
		self.console = console
		self.logger = logger
		self.batches = BatchRepository(database)
		self.jobs = JobRepository(database)
		self.accounts = AccountRepository(database)
		self.events = EventRepository(database)
		self.session_checker = SessionChecker(settings.element_timeout_ms)

	async def recover_unfinished(self, page: Page) -> None:
		unfinished = self.jobs.get_unfinished()
		unreported = self._get_unreported_jobs()
		if not unfinished and not unreported:
			return
		# One guarded scan of the live list (navigate only if the tab is
		# elsewhere); recovery must never crash startup.
		try:
			if "my.exness.com/pa/trading/accounts" not in (page.url or "").lower():
				await open_accounts_page(page, self.settings.exness_url)
			current = await self._account_identifiers(page)
		except Exception as error:
			self.console.print(f"[yellow][RECOVERY] Accounts list unavailable: {error}[/yellow]")
			return
		if unfinished:
			self.console.print(f"[yellow][RECOVERY] {len(unfinished)} unfinished job(s) found.[/yellow]")
		for job in unfinished:
			baseline = set(json.loads(job["baseline_accounts_json"] or "[]"))
			result = reconcile(baseline, current)
			if result.candidate is None:
				self.jobs.save_error(job["id"], "MANUAL_REVIEW_REQUIRED", "Interrupted job requires operator reconciliation", JobStatus.MANUAL_REVIEW)
				self.events.log_event("MANUAL_REVIEW_REQUIRED", level="WARNING", job_id=job["id"], message="Interrupted job could not be reconciled")
				continue
			if self.accounts.get_by_job(job["id"]):
				continue
			if not job["password_encrypted"]:
				self.jobs.save_error(job["id"], "MANUAL_REVIEW_REQUIRED", "Recovered account has no stored password", JobStatus.MANUAL_REVIEW)
				continue
			try:
				password = EncryptionService(self.settings.encryption_key).decrypt(job["password_encrypted"])
				for _ in range(3):
					try:
						save_account_and_verify(result.candidate, password, self.settings.nickname, self.settings.export_directory)
						break
					except (OSError, ValueError):
						continue
				else:
					self.jobs.save_error(job["id"], "REPORT_WRITE_FAILED", "Recovered account report could not be verified", JobStatus.MANUAL_REVIEW)
					continue
			except Exception:
				self.jobs.save_error(job["id"], "REPORT_WRITE_FAILED", "Recovered account report could not be verified", JobStatus.MANUAL_REVIEW)
				continue
			account = CreatedAccount(
				job_id=job["id"], mt5_number=result.candidate,
				password_encrypted=job["password_encrypted"], nickname=self.settings.nickname,
				account_mode=self.settings.account_mode, account_type=self.settings.account_type,
				platform=self.settings.platform, currency=self.settings.currency,
				demo_deposit=self.settings.demo_deposit,
				server=await AccountDetailsPage(page).get_server(), created_at="",
			)
			self.accounts.create_verified_account(account)
			self.jobs.update_status(job["id"], JobStatus.SUCCESS)
			self.events.log_event("ACCOUNT_VERIFIED", job_id=job["id"], message="Recovered after restart")
		if unreported:
			self.console.print(
				f"[yellow][RECOVERY] {len(unreported)} submitted job(s) missing a report row.[/yellow]"
			)
			for job in unreported:
				await self._recover_unreported_job(job, current)

	def _get_unreported_jobs(self):
		placeholders = ", ".join("?" for _ in SUBMITTED_ERROR_CODES)
		return self.database.connect().execute(
			f"SELECT * FROM jobs WHERE status = ? AND error_code IN ({placeholders})",
			(JobStatus.MANUAL_REVIEW.value, *SUBMITTED_ERROR_CODES),
		).fetchall()

	async def _recover_unreported_job(self, job, current: set[str]) -> None:
		# STEP 10-12 for a job that submitted but died before its CSV row
		# was verified: diff the stored baseline against the live list,
		# then write + verify the row with the stored password. The same
		# report verification as a live run is never skipped.
		if self.accounts.get_by_job(job["id"]):
			self.jobs.update_status(job["id"], JobStatus.SUCCESS)
			return
		if not job["password_encrypted"] or not job["baseline_accounts_json"]:
			return
		baseline = set(json.loads(job["baseline_accounts_json"]))
		result = reconcile(baseline, current)
		if result.candidate is None:
			# Zero or multiple new accounts: ambiguous, leave for operator.
			self.events.log_event(
				"RECOVERY_SKIPPED", level="WARNING", job_id=job["id"],
				message=result.reason or "NO_NEW_ACCOUNT",
			)
			return
		mt5_number = result.candidate
		existing = self.database.connect().execute(
			"SELECT job_id FROM created_accounts WHERE mt5_number = ?", (mt5_number,)
		).fetchone()
		if existing is not None:
			# Already recorded (possibly under another job): never duplicate.
			if existing["job_id"] == job["id"]:
				self.jobs.update_status(job["id"], JobStatus.SUCCESS)
			return
		try:
			password = EncryptionService(self.settings.encryption_key).decrypt(job["password_encrypted"])
			for _ in range(3):
				try:
					save_account_and_verify(mt5_number, password, self.settings.nickname, self.settings.export_directory)
					break
				except (OSError, ValueError):
					continue
			else:
				return  # disk still failing; stay MANUAL_REVIEW for operator
			account = CreatedAccount(
				job_id=job["id"], mt5_number=mt5_number,
				password_encrypted=job["password_encrypted"], nickname=self.settings.nickname,
				account_mode=self.settings.account_mode, account_type=self.settings.account_type,
				platform=self.settings.platform, currency=self.settings.currency,
				demo_deposit=self.settings.demo_deposit, server=None, created_at="",
			)
			self.accounts.create_verified_account(account)
		except Exception as error:
			self.console.print(f"[yellow][RECOVERY] Could not record job {job['id']}: {error}[/yellow]")
			return
		self.jobs.update_status(job["id"], JobStatus.SUCCESS)
		self.events.log_event("ACCOUNT_VERIFIED", job_id=job["id"], message="Report recovered for submitted job")
		self.console.print(f"[green][RECOVERY] report/accounts.csv updated for MT5 {mt5_number}.[/green]")

	async def _account_identifiers(self, page: Page) -> set[str]:
		from pages.accounts_page import AccountsPage
		return await AccountsPage(page, self.settings.element_timeout_ms).get_account_identifiers()

	async def wait_for_authentication(self, page: Page) -> None:
		# Spec section 2: detect session; if not authenticated, pause and wait
		# for manual action (never automate login/OTP/CAPTCHA). Polling here
		# is only the manual-action wait loop, not page synchronization.
		waiting_displayed = False
		while True:
			status = await self.session_checker.check(page)
			if status == SessionStatus.AUTHENTICATED:
				self.console.print("[green][READY] Authenticated Exness session detected.[/green]")
				self.events.log_event("SESSION_AUTHENTICATED")
				# Ensure we are on the trading accounts page after login.
				try:
					current_url = (page.url or "").lower()
				except Exception:
					current_url = ""
				if "trading/accounts" not in current_url:
					await open_accounts_page(page, self.settings.exness_url)
				return
			if status == SessionStatus.MANUAL_ACTION_REQUIRED:
				self.console.print("[yellow][MANUAL ACTION] Complete the security challenge in the browser.[/yellow]")
			elif not waiting_displayed:
				self.console.print("[yellow][WAITING] Please log in manually in the browser.[/yellow]")
				self.events.log_event("WAITING_FOR_LOGIN")
				waiting_displayed = True
			await asyncio.sleep(self.settings.session_check_interval_seconds)

	async def run_batch(self, page: Page, count: int) -> None:
		batch_id = self.batches.create(count)
		self.jobs.create_batch_jobs(batch_id, count)
		self.batches.update_status(batch_id, BatchStatus.RUNNING)
		processor = JobProcessor(self.database, self.settings, self.logger)
		for _ in range(count):
			job_id = self.jobs.claim_next_job(batch_id)
			if job_id is None:
				break
			status = await processor.process(page, job_id)
			# Never log passwords/credentials: JobStatus only.
			self.console.print(f"Job finished: {job_id} -> {status}")
			self.logger.info("job finished: %s -> %s", job_id, status)
			if status != JobStatus.SUCCESS:
				break
			# Speed rule 3/6: NO inter-job navigation/reload here. The next
			# JobProcessor.process() call conditionally reuses the current
			# page (it only navigates when the browser is not already on
			# the accounts list), so no redundant Personal Area reload per
			# account and no duplicated state wait.
		rows = self.database.connect().execute(
			"SELECT status, COUNT(*) AS count FROM jobs WHERE batch_id = ? GROUP BY status", (batch_id,)
		).fetchall()
		counts = {row["status"]: row["count"] for row in rows}
		self.batches.update_counts(batch_id, counts.get("SUCCESS", 0), counts.get("FAILED", 0), counts.get("MANUAL_REVIEW", 0))
		self.batches.update_status(batch_id, BatchStatus.COMPLETED)
