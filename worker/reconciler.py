from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationResult:
	new_accounts: set[str]
	candidate: str | None
	requires_manual_review: bool
	reason: str | None = None


def reconcile(baseline: set[str], current: set[str]) -> ReconciliationResult:
	new_accounts = current - baseline
	if len(new_accounts) == 1:
		return ReconciliationResult(new_accounts, next(iter(new_accounts)), False)
	if not new_accounts:
		return ReconciliationResult(new_accounts, None, True, "ACCOUNT_RECONCILIATION_FAILED")
	return ReconciliationResult(new_accounts, None, True, "MULTIPLE_NEW_ACCOUNTS")
