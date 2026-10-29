from database.repositories.batch_repository import utc_now
from database.connection import Database
from models.enums import JobStatus
import uuid


class JobRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_batch_jobs(self, batch_id: str, count: int) -> list[str]:
        job_ids = [str(uuid.uuid4()) for _ in range(count)]
        timestamp = utc_now()
        with self.database.transaction() as connection:
            connection.executemany(
                "INSERT INTO jobs (id, batch_id, job_number, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                [(job_id, batch_id, number, timestamp, timestamp) for number, job_id in enumerate(job_ids, 1)],
            )
        return job_ids

    def claim_next_job(self, batch_id: str) -> str | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id FROM jobs WHERE batch_id = ? AND status = ? ORDER BY job_number LIMIT 1",
                (batch_id, JobStatus.PENDING.value),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status = ?, attempt_count = attempt_count + 1, updated_at = ? WHERE id = ? AND status = ?",
                (JobStatus.CLAIMED.value, utc_now(), row["id"], JobStatus.PENDING.value),
            )
            return row["id"]

    def update_status(self, job_id: str, status: JobStatus) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, completed_at = CASE WHEN ? IN ('SUCCESS', 'FAILED', 'MANUAL_REVIEW') THEN ? ELSE completed_at END WHERE id = ?",
                (status.value, utc_now(), status.value, utc_now(), job_id),
            )

    def set_password(self, job_id: str, password_encrypted: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET password_encrypted = ?, updated_at = ? WHERE id = ?",
                (password_encrypted, utc_now(), job_id),
            )

    def set_baseline(self, job_id: str, baseline_accounts_json: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET baseline_accounts_json = ?, updated_at = ? WHERE id = ?",
                (baseline_accounts_json, utc_now(), job_id),
            )

    def save_error(self, job_id: str, error_code: str, error_message: str, status: JobStatus) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error_code = ?, error_message = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (status.value, error_code, error_message, utc_now(), utc_now(), job_id),
            )

    def get(self, job_id: str):
        return self.database.connect().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    def get_unfinished(self, batch_id: str | None = None):
        unfinished = (
            "CLAIMED", "PRECHECK", "BASELINE_CAPTURED", "OPENING_FORM", "CONFIGURING",
            "VALIDATING", "READY_TO_SUBMIT", "SUBMITTING", "VERIFYING", "RECONCILING",
        )
        placeholders = ", ".join("?" for _ in unfinished)
        query = f"SELECT * FROM jobs WHERE status IN ({placeholders})"
        parameters: tuple[str, ...] = unfinished
        if batch_id is not None:
            query += " AND batch_id = ?"
            parameters += (batch_id,)
        return self.database.connect().execute(query, parameters).fetchall()
