#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "webactueel-transcribe"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_dir() -> Path:
    raw = str(os.environ.get("TRANSCRIBE_STATE_DIR") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_STATE_DIR


def connect() -> sqlite3.Connection:
    path = state_dir() / "history.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed (
            video_id TEXT NOT NULL,
            requested_language TEXT NOT NULL,
            source_type TEXT NOT NULL,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            caption_language TEXT,
            caption_kind TEXT,
            caption_format TEXT,
            cue_count INTEGER,
            transcript_sha256 TEXT,
            transcript_chars INTEGER NOT NULL DEFAULT 0,
            transcript_text TEXT,
            first_processed_at TEXT NOT NULL,
            last_processed_at TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 1,
            last_cache_hit INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (video_id, requested_language)
        )
    """)
    return conn


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached_transcript(conn: sqlite3.Connection, video_id: str, language: str) -> dict | None:
    row = conn.execute("SELECT * FROM processed WHERE video_id=? AND requested_language=? AND status='ok'", (video_id, language)).fetchone()
    if row is None:
        return None
    text = row["transcript_text"]
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = text.rstrip() + "\n"
    if digest(normalized) != row["transcript_sha256"] or len(normalized) != row["transcript_chars"]:
        conn.execute("DELETE FROM processed WHERE video_id=? AND requested_language=?", (video_id, language))
        conn.commit()
        return None
    conn.execute("UPDATE processed SET last_cache_hit=1, last_processed_at=? WHERE video_id=? AND requested_language=?", (utc_now(), video_id, language))
    conn.commit()
    return {
        "text": normalized,
        "caption": {"language": row["caption_language"], "kind": row["caption_kind"], "format": row["caption_format"], "cue_count": row["cue_count"]},
        "sha256": row["transcript_sha256"],
    }


def store_result(conn: sqlite3.Connection, *, video_id: str, language: str, url: str, status: str, caption: dict | None, transcript: str | None, upload_date: str = "", title: str = "") -> None:
    now = utc_now()
    current = conn.execute("SELECT first_processed_at, attempt_count FROM processed WHERE video_id=? AND requested_language=?", (video_id, language)).fetchone()
    first = current["first_processed_at"] if current else now
    attempts = int(current["attempt_count"]) + 1 if current else 1
    normalized = transcript.rstrip() + "\n" if transcript else None
    sha = digest(normalized) if normalized else None
    caption = caption or {}
    conn.execute("""
        INSERT INTO processed (
            video_id, requested_language, source_type, url, status,
            caption_language, caption_kind, caption_format, cue_count,
            transcript_sha256, transcript_chars, transcript_text,
            first_processed_at, last_processed_at, attempt_count, last_cache_hit
        ) VALUES (?, ?, 'video', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(video_id, requested_language) DO UPDATE SET
            source_type='video', url=excluded.url, status=excluded.status,
            caption_language=excluded.caption_language, caption_kind=excluded.caption_kind,
            caption_format=excluded.caption_format, cue_count=excluded.cue_count,
            transcript_sha256=excluded.transcript_sha256, transcript_chars=excluded.transcript_chars,
            transcript_text=excluded.transcript_text, last_processed_at=excluded.last_processed_at,
            attempt_count=excluded.attempt_count, last_cache_hit=0
    """, (video_id, language, url, status, caption.get("language"), caption.get("kind"), caption.get("format"), caption.get("cue_count"), sha, len(normalized or ""), normalized, first, now, attempts))
    conn.commit()


def export_index(conn: sqlite3.Connection, path: Path) -> dict:
    rows = conn.execute("""
        SELECT video_id, requested_language, url, status, caption_language, caption_kind,
               caption_format, cue_count, transcript_sha256, transcript_chars,
               first_processed_at, last_processed_at, attempt_count, last_cache_hit
        FROM processed ORDER BY last_processed_at DESC
    """).fetchall()
    status_counts = {}
    unique_videos = set()
    items = []
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        unique_videos.add(row["video_id"])
        items.append({
            "video_id": row["video_id"],
            "requested_language": row["requested_language"],
            "url": row["url"],
            "status": status,
            "caption": {
                "language": row["caption_language"],
                "kind": row["caption_kind"],
                "format": row["caption_format"],
                "cue_count": row["cue_count"],
            } if status == "ok" else None,
            "transcript_sha256": row["transcript_sha256"],
            "transcript_chars": row["transcript_chars"],
            "first_processed_at": row["first_processed_at"],
            "last_processed_at": row["last_processed_at"],
            "attempt_count": row["attempt_count"],
            "last_cache_hit": bool(row["last_cache_hit"]),
        })
    payload = {
        "schema_version": "2.0",
        "generated_at": utc_now(),
        "unique_videos": len(unique_videos),
        "processed_entries": len(rows),
        "captions_done": status_counts.get("ok", 0),
        "status_counts": status_counts,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
