from dataclasses import dataclass

from models.enums import BatchStatus


@dataclass(frozen=True)
class Batch:
    id: str
    requested_count: int
    successful_count: int = 0
    failed_count: int = 0
    manual_review_count: int = 0
    status: BatchStatus = BatchStatus.PENDING
    created_at: str = ""
    completed_at: str | None = None
