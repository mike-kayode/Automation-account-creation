import json

from database.connection import Database
from database.repositories.batch_repository import utc_now


class EventRepository:
    def __init__(self, database: Database):
        self.database = database

    def log_event(self, event: str, level: str = "INFO", job_id: str | None = None,
                  message: str | None = None, metadata: dict | None = None) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO events (job_id, level, event, message, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, level, event, message, json.dumps(metadata) if metadata else None, utc_now()),
            )
