from models.enums import JobStatus


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
	JobStatus.PENDING: {JobStatus.CLAIMED},
	JobStatus.CLAIMED: {JobStatus.PRECHECK, JobStatus.PAUSED},
	JobStatus.PRECHECK: {JobStatus.BASELINE_CAPTURED, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
	JobStatus.BASELINE_CAPTURED: {JobStatus.OPENING_FORM, JobStatus.MANUAL_REVIEW},
	JobStatus.OPENING_FORM: {JobStatus.CONFIGURING, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
	JobStatus.CONFIGURING: {JobStatus.VALIDATING, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
	JobStatus.VALIDATING: {JobStatus.READY_TO_SUBMIT, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
	JobStatus.READY_TO_SUBMIT: {JobStatus.SUBMITTING, JobStatus.MANUAL_REVIEW},
	JobStatus.SUBMITTING: {JobStatus.VERIFYING, JobStatus.MANUAL_REVIEW, JobStatus.PAUSED},
	JobStatus.VERIFYING: {JobStatus.RECONCILING, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
	JobStatus.RECONCILING: {JobStatus.SUCCESS, JobStatus.MANUAL_REVIEW, JobStatus.FAILED},
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
	return target in ALLOWED_TRANSITIONS.get(current, set())
