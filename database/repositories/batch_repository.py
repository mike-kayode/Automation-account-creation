from datetime import datetime, timezone
import uuid

from database.connection import Database
from models.enums import BatchStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BatchRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, requested_count: int) -> str:
        if requested_count <= 0:
            raise ValueError("requested_count must be greater than zero")
        batch_id = str(uuid.uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO batches (id, requested_count, created_at) VALUES (?, ?, ?)",
                (batch_id, requested_count, utc_now()),
            )
        return batch_id

    def get(self, batch_id: str):
        return self.database.connect().execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()

    def update_status(self, batch_id: str, status: BatchStatus) -> None:
        with self.database.transaction() as connection:
            connection.execute("UPDATE batches SET status = ? WHERE id = ?", (status.value, batch_id))

    def update_counts(self, batch_id: str, successful: int, failed: int, manual_review: int) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE batches SET successful_count = ?, failed_count = ?, manual_review_count = ? WHERE id = ?",
                (successful, failed, manual_review, batch_id),
            )
