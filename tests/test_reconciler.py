from models.enums import JobStatus
from worker.reconciler import reconcile
from worker.state_machine import can_transition


def test_reconcile_requires_exactly_one_new_account():
    result = reconcile({"100000001"}, {"100000001", "100000002"})
    assert result.candidate == "100000002"
    assert not result.requires_manual_review


def test_reconcile_rejects_zero_or_multiple_new_accounts():
    empty = reconcile({"100000001"}, {"100000001"})
    multiple = reconcile({"100000001"}, {"100000001", "100000002", "100000003"})
    assert empty.requires_manual_review
    assert empty.reason == "ACCOUNT_RECONCILIATION_FAILED"
    assert multiple.requires_manual_review
    assert multiple.reason == "MULTIPLE_NEW_ACCOUNTS"


def test_state_machine_does_not_allow_resubmit_from_uncertain_submission():
    assert can_transition(JobStatus.SUBMITTING, JobStatus.MANUAL_REVIEW)
    assert not can_transition(JobStatus.SUBMITTING, JobStatus.READY_TO_SUBMIT)
