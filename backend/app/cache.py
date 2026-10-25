"""Analyses are expensive and deterministic enough to keep: one row per (video, engine)."""

import sqlite3
from contextlib import closing

from .config import CACHE_DB
from .models import Analysis, LibraryItem


def _connect() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyses ("
        " video_id TEXT NOT NULL, engine TEXT NOT NULL, body TEXT NOT NULL,"
        " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (video_id, engine))"
    )
    return conn


def get(video_id: str, engine: str) -> Analysis | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT body FROM analyses WHERE video_id = ? AND engine = ?", (video_id, engine)
        ).fetchone()
    return Analysis.model_validate_json(row[0]) if row else None


def put(analysis: Analysis) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyses (video_id, engine, body) VALUES (?, ?, ?)",
            (analysis.video_id, analysis.engine, analysis.model_dump_json()),
        )


def recent(limit: int = 100) -> list[LibraryItem]:
    """Most recently analyzed lectures, one entry per video (newest engine wins)."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT body, created_at FROM analyses ORDER BY created_at DESC, rowid DESC").fetchall()
    items: dict[str, LibraryItem] = {}
    for body, created_at in rows:
        a = Analysis.model_validate_json(body)
        if a.video_id not in items:
            items[a.video_id] = LibraryItem(
                video_id=a.video_id, title=a.title, duration=a.duration, engine=a.engine, analyzed_at=created_at
            )
        if len(items) >= limit:
            break
    return list(items.values())


def delete(video_id: str) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM analyses WHERE video_id = ?", (video_id,))
