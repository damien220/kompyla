from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    wiki_path   TEXT    NOT NULL UNIQUE,
    page_type   TEXT,
    sources     TEXT,           -- JSON list of raw/ relative paths
    confidence  REAL    DEFAULT 0.5,
    created_at  TEXT,
    updated_at  TEXT,
    tags        TEXT            -- JSON list
);

CREATE TABLE IF NOT EXISTS raw_docs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT    NOT NULL UNIQUE,
    ingested_at     TEXT,
    compiled_at     TEXT,           -- NULL until compiled
    size_bytes      INTEGER,
    title           TEXT,
    url             TEXT,
    source_type     TEXT,
    relevance_score REAL,
    content_hash    TEXT
);
CREATE INDEX IF NOT EXISTS idx_raw_url ON raw_docs(url);
CREATE INDEX IF NOT EXISTS idx_raw_hash ON raw_docs(content_hash);
"""

# Columns added after Phase 1 — applied via _migrate() to existing DBs
_RAW_DOC_MIGRATIONS = {
    "title": "TEXT",
    "url": "TEXT",
    "source_type": "TEXT",
    "relevance_score": "REAL",
    "content_hash": "TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(raw_docs)")}
    for col, ddl in _RAW_DOC_MIGRATIONS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE raw_docs ADD COLUMN {col} {ddl}")
    conn.commit()


class MetaIndex:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        _migrate(self._conn)

    # --- raw docs ---

    def upsert_raw_doc(
        self,
        path: Path,
        *,
        url: str | None = None,
        source_type: str | None = None,
        relevance_score: float | None = None,
        content_hash: str | None = None,
        title: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO raw_docs "
            "(path, ingested_at, size_bytes, title, url, source_type, relevance_score, content_hash) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "ingested_at=excluded.ingested_at, size_bytes=excluded.size_bytes, "
            "title=COALESCE(excluded.title, raw_docs.title), "
            "url=COALESCE(excluded.url, raw_docs.url), "
            "source_type=COALESCE(excluded.source_type, raw_docs.source_type), "
            "relevance_score=COALESCE(excluded.relevance_score, raw_docs.relevance_score), "
            "content_hash=COALESCE(excluded.content_hash, raw_docs.content_hash)",
            (
                str(path), _now(), path.stat().st_size,
                title, url, source_type, relevance_score, content_hash,
            ),
        )
        self._conn.commit()

    def mark_compiled(self, raw_path: Path) -> None:
        self._conn.execute(
            "UPDATE raw_docs SET compiled_at=? WHERE path=?",
            (_now(), str(raw_path)),
        )
        self._conn.commit()

    def pending_raw_docs(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM raw_docs WHERE compiled_at IS NULL ORDER BY ingested_at"
        ).fetchall()

    def all_raw_docs(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM raw_docs ORDER BY ingested_at"
        ).fetchall()

    def find_by_url(self, url: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM raw_docs WHERE url=?", (url,)
        ).fetchone()

    def find_by_hash(self, content_hash: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM raw_docs WHERE content_hash=?", (content_hash,)
        ).fetchone()

    # --- wiki pages ---

    def upsert_page(
        self,
        title: str,
        wiki_path: Path,
        page_type: str,
        sources: list[str],
        confidence: float,
        tags: list[str],
    ) -> None:
        now = _now()
        self._conn.execute(
            "INSERT INTO pages "
            "(title, wiki_path, page_type, sources, confidence, created_at, updated_at, tags) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(wiki_path) DO UPDATE SET "
            "title=excluded.title, page_type=excluded.page_type, "
            "sources=excluded.sources, confidence=excluded.confidence, "
            "updated_at=excluded.updated_at, tags=excluded.tags",
            (
                title, str(wiki_path), page_type,
                json.dumps(sources), confidence,
                now, now, json.dumps(tags),
            ),
        )
        self._conn.commit()

    def all_pages(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM pages ORDER BY title"
        ).fetchall()

    def close(self) -> None:
        self._conn.close()
