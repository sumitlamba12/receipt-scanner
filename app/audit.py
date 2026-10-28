"""Lightweight SQLite audit trail: one row per processed image.

Gives two things a plain "rename and move the file" pipeline doesn't have on
its own, both of which matter once you're doing thousands of receipts a day
for a company rather than eyeballing a handful of files:
  - A queryable record of what was processed and when, for support/audit.
  - Duplicate detection: the same tracking number showing up twice usually
    means the same receipt got uploaded/photographed twice, which is worth
    flagging even though the file itself is still processed normally.
"""

import sqlite3
import threading
from datetime import datetime, timezone

from app import config

_lock = threading.Lock()
_schema_ready_for = set()  # keyed by db path; supports tests pointing at different temp DBs


def _connect():
    conn = sqlite3.connect(config.AUDIT_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema():
    db_path = config.AUDIT_DB_PATH
    if db_path in _schema_ready_for:
        return
    with _lock:
        if db_path in _schema_ready_for:
            return
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_filename TEXT NOT NULL,
                    value TEXT,
                    source TEXT,
                    status TEXT NOT NULL,
                    dest_path TEXT,
                    processed_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_value ON receipts(value)")
            conn.commit()
        finally:
            conn.close()
        _schema_ready_for.add(db_path)


def is_duplicate(value: str) -> bool:
    """True if this tracking number was already successfully processed before."""
    if not value:
        return False
    _ensure_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT 1 FROM receipts WHERE value = ? AND status = 'processed' LIMIT 1",
            (value,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def record(original_filename: str, value, source, status: str, dest_path: str) -> None:
    _ensure_schema()
    conn = _connect()
    try:
        with _lock:
            conn.execute(
                """
                INSERT INTO receipts (original_filename, value, source, status, dest_path, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (original_filename, value, source, status, dest_path, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
    finally:
        conn.close()
