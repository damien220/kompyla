"""Persistent user feedback store (SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VALID_SIGNALS = frozenset(["wrong", "outdated", "excellent", "unclear"])

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    page_title  TEXT NOT NULL,
    signal      TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_title ON feedback(page_title);
"""


class FeedbackStore:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, page_title: str, signal: str, note: str = "") -> None:
        if signal not in VALID_SIGNALS:
            raise ValueError(f"signal must be one of {sorted(VALID_SIGNALS)}, got {signal!r}")
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO feedback (page_title, signal, note, created_at) VALUES (?,?,?,?)",
            (page_title, signal, note or None, now),
        )
        self._conn.commit()

    def for_page(self, page_title: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM feedback WHERE page_title=? ORDER BY created_at",
            (page_title,),
        ).fetchall()

    def all_feedback(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC"
        ).fetchall()

    def signal_counts(self, page_title: str) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT signal, COUNT(*) as n FROM feedback WHERE page_title=? GROUP BY signal",
            (page_title,),
        ).fetchall()
        return {r["signal"]: r["n"] for r in rows}

    def close(self) -> None:
        self._conn.close()
