from dataclasses import dataclass


@dataclass(frozen=True)
class CreatedAccount:
    job_id: str
    mt5_number: str
    password_encrypted: str
    nickname: str
    account_mode: str
    account_type: str
    platform: str
    currency: str
    demo_deposit: int
    server: str | None
    created_at: str
