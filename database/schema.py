SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    requested_count INTEGER NOT NULL CHECK (requested_count > 0),
    successful_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    manual_review_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    job_number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    password_encrypted TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    baseline_accounts_json TEXT,
    submission_started_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(batch_id, job_number),
    FOREIGN KEY(batch_id) REFERENCES batches(id)
);

CREATE TABLE IF NOT EXISTS created_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    mt5_number TEXT UNIQUE NOT NULL,
    password_encrypted TEXT NOT NULL,
    nickname TEXT NOT NULL,
    account_mode TEXT NOT NULL,
    account_type TEXT NOT NULL,
    platform TEXT NOT NULL,
    currency TEXT NOT NULL,
    demo_deposit INTEGER NOT NULL,
    server TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    message TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_batch_status ON jobs(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
"""
