from models.account import CreatedAccount
from models.enums import JobStatus
from database.connection import Database
from database.repositories.account_repository import AccountRepository
from database.repositories.batch_repository import BatchRepository
from database.repositories.job_repository import JobRepository


def test_database_initializes_and_enforces_foreign_keys(tmp_path):
    database = Database(tmp_path / "worker.db")
    database.initialize()
    assert database.connect().execute("PRAGMA foreign_keys").fetchone()[0] == 1

    batches = BatchRepository(database)
    jobs = JobRepository(database)
    accounts = AccountRepository(database)
    batch_id = batches.create(2)
    job_ids = jobs.create_batch_jobs(batch_id, 2)

    assert jobs.claim_next_job(batch_id) == job_ids[0]
    assert jobs.get(job_ids[0])["status"] == JobStatus.CLAIMED.value
    assert jobs.claim_next_job(batch_id) == job_ids[1]
    assert jobs.claim_next_job(batch_id) is None

    accounts.create_verified_account(CreatedAccount(
        job_id=job_ids[0], mt5_number="203456781", password_encrypted="encrypted",
        nickname="NairaTrader 1.5", account_mode="DEMO", account_type="PRO",
        platform="MT5", currency="NGN", demo_deposit=1_500_000, server=None, created_at="now",
    ))
    assert accounts.get_by_job(job_ids[0])["mt5_number"] == "203456781"
    database.close()
