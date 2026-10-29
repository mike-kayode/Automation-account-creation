from dataclasses import dataclass

from models.enums import JobStatus


@dataclass(frozen=True)
class Job:
    id: str
    batch_id: str
    job_number: int
    status: JobStatus = JobStatus.PENDING
    password_encrypted: str | None = None
    attempt_count: int = 0
    baseline_accounts_json: str | None = None
    submission_started_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None
