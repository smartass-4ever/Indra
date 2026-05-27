"""
SQLite snapshot store for Indra.

Persists web content snapshots + hashes so change detection
works across restarts and agent runs.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional


_DDL = """
CREATE TABLE IF NOT EXISTS web_snapshots (
    url          TEXT    PRIMARY KEY,
    content_hash TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    fetched_at   REAL    NOT NULL,
    change_count INTEGER NOT NULL DEFAULT 0,
    last_changed REAL
);
"""


class WebSnapshotStore:
    """
    Lightweight SQLite store — one row per watched URL.
    Thread-safe via check_same_thread=False + WAL mode.
    """

    def __init__(self, db_path: str = "indra_snapshots.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_DDL)
        self._conn.commit()

    def get(self, url: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT content_hash, content, fetched_at, change_count, last_changed "
            "FROM web_snapshots WHERE url = ?",
            (url,),
        ).fetchone()
        if row:
            return {
                "hash":         row[0],
                "content":      row[1],
                "fetched_at":   row[2],
                "change_count": row[3],
                "last_changed": row[4],
            }
        return None

    def upsert(self, url: str, content_hash: str, content: str, changed: bool) -> None:
        now      = time.time()
        existing = self.get(url)
        count    = (existing["change_count"] + 1) if (existing and changed) else (existing["change_count"] if existing else 0)
        last_ch  = now if changed else (existing["last_changed"] if existing else None)

        self._conn.execute(
            """
            INSERT INTO web_snapshots (url, content_hash, content, fetched_at, change_count, last_changed)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                content_hash = excluded.content_hash,
                content      = excluded.content,
                fetched_at   = excluded.fetched_at,
                change_count = excluded.change_count,
                last_changed = excluded.last_changed
            """,
            (url, content_hash, content[:100_000], now, count, last_ch),
        )
        self._conn.commit()

    def all_urls(self) -> list:
        rows = self._conn.execute("SELECT url, change_count, last_changed FROM web_snapshots").fetchall()
        return [{"url": r[0], "change_count": r[1], "last_changed": r[2]} for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
