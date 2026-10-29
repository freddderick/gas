"""SQLite storage: installs, deduplicated location cells, the derived
pressure_msl series, alert state, and alert history.

Only derived values are stored (one pressure_msl number per cell per hour),
never raw provider responses. Locations are stored snapped to the grid, never
at the exact coordinates the device sent.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS cells (
    id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    created_at INTEGER NOT NULL,
    last_fetch_at INTEGER,
    last_success_at INTEGER,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS samples (
    cell_id TEXT NOT NULL REFERENCES cells(id) ON DELETE CASCADE,
    ts INTEGER NOT NULL,
    pressure_msl REAL NOT NULL,
    PRIMARY KEY (cell_id, ts)
);

CREATE TABLE IF NOT EXISTS installs (
    id TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL,
    apns_token TEXT,
    apns_environment TEXT NOT NULL DEFAULT 'production',
    cell_id TEXT REFERENCES cells(id),
    location_name TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    settings_json TEXT NOT NULL,
    last_evaluated_ts INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS installs_cell ON installs(cell_id);

CREATE TABLE IF NOT EXISTS alert_state (
    install_id TEXT NOT NULL REFERENCES installs(id) ON DELETE CASCADE,
    direction TEXT NOT NULL,
    alerted_level REAL,
    alerted_ts INTEGER,
    PRIMARY KEY (install_id, direction)
);

CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    install_id TEXT NOT NULL REFERENCES installs(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    direction TEXT NOT NULL,
    window_hours INTEGER NOT NULL,
    threshold_hpa REAL NOT NULL,
    change_hpa REAL NOT NULL,
    pressure_hpa REAL NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS alert_history_install ON alert_history(install_id, created_at);

CREATE TABLE IF NOT EXISTS api_usage (
    month TEXT PRIMARY KEY,
    calls INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A serialized transaction. The app is one process with a handful of
        writers, so a single connection behind a lock is plenty."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
