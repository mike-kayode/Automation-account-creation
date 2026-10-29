from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from database.schema import SCHEMA_SQL


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self.connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
        return self.connection

    def initialize(self) -> None:
        connection = self.connect()
        connection.executescript(SCHEMA_SQL)
        connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
