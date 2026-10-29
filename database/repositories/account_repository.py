from database.connection import Database
from database.repositories.batch_repository import utc_now
from models.account import CreatedAccount


class AccountRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_verified_account(self, account: CreatedAccount) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO created_accounts
                (job_id, mt5_number, password_encrypted, nickname, account_mode,
                 account_type, platform, currency, demo_deposit, server, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account.job_id, account.mt5_number, account.password_encrypted, account.nickname,
                 account.account_mode, account.account_type, account.platform, account.currency,
                 account.demo_deposit, account.server, account.created_at or utc_now()),
            )

    def get_by_job(self, job_id: str):
        return self.database.connect().execute(
            "SELECT * FROM created_accounts WHERE job_id = ?", (job_id,)
        ).fetchone()
