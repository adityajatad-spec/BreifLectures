"""Analyses are expensive and deterministic enough to keep: one row per (video, engine)."""

import sqlite3
from contextlib import closing

from .config import CACHE_DB
from .models import Analysis


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
