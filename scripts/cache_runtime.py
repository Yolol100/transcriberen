#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import captions_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "webactueel-transcribe"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_dir() -> Path:
    raw = str(os.environ.get("TRANSCRIBE_STATE_DIR") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_STATE_DIR


def db_path() -> Path:
    return state_dir() / "history.sqlite3"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """
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
        """
    )
    return conn


def load_request() -> dict:
    request_file = Path(os.environ.get("REQUEST_FILE", "resolved-request.json"))
    return json.loads(request_file.read_text(encoding="utf-8"))


def transcript_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def cached_row(conn: sqlite3.Connection, request: dict) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM processed
        WHERE video_id = ? AND requested_language = ? AND status = 'ok'
        """,
        (request["video_id"], request.get("language", "auto")),
    ).fetchone()


def row_is_usable(row: sqlite3.Row) -> bool:
    text = row["transcript_text"]
    digest = row["transcript_sha256"]
    if not isinstance(text, str) or not text.strip() or not isinstance(digest, str):
        return False
    normalized = text.rstrip() + "\n"
    return transcript_digest(normalized) == digest and len(normalized) == row["transcript_chars"]


def write_cached_result(request: dict, row: sqlite3.Row) -> None:
    normalized = str(row["transcript_text"]).rstrip() + "\n"
    result = runtime.base_result(request)
    result["status"] = "ok"
    result["caption"] = {
        "language": row["caption_language"],
        "kind": row["caption_kind"],
        "format": row["caption_format"],
        "cue_count": row["cue_count"],
    }
    result["transcript_sha256"] = row["transcript_sha256"]
    result["transcript_chars"] = len(normalized)
    result["cache_hit"] = True
    runtime.write_result(result, normalized)


def precheck() -> int:
    request = load_request()
    with connect() as conn:
        row = cached_row(conn, request)
        if row is not None and row_is_usable(row):
            write_cached_result(request, row)
            set_output("hit", "true")
            print(json.dumps({
                "request_id": request["request_id"],
                "video_id": request["video_id"],
                "cache_hit": True,
            }))
            return 0
        if row is not None:
            conn.execute(
                "DELETE FROM processed WHERE video_id = ? AND requested_language = ?",
                (request["video_id"], request.get("language", "auto")),
            )
            conn.commit()
    set_output("hit", "false")
    print(json.dumps({
        "request_id": request["request_id"],
        "video_id": request["video_id"],
        "cache_hit": False,
    }))
    return 0


def load_result() -> dict:
    path = RESULTS / "result.json"
    if not path.is_file():
        raise RuntimeError("results/result.json does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_result(conn: sqlite3.Connection, request: dict, result: dict) -> None:
    now = utc_now()
    current = conn.execute(
        "SELECT first_processed_at, attempt_count FROM processed WHERE video_id = ? AND requested_language = ?",
        (request["video_id"], request.get("language", "auto")),
    ).fetchone()
    first = current["first_processed_at"] if current else now
    attempts = int(current["attempt_count"]) + 1 if current else 1
    caption = result.get("caption") if isinstance(result.get("caption"), dict) else {}
    transcript_text = None
    if result.get("status") == "ok":
        path = RESULTS / "transcript.txt"
        transcript_text = path.read_text(encoding="utf-8")
        normalized = transcript_text.rstrip() + "\n"
        if transcript_digest(normalized) != result.get("transcript_sha256"):
            raise RuntimeError("refusing to cache transcript with checksum mismatch")
        transcript_text = normalized

    conn.execute(
        """
        INSERT INTO processed (
            video_id, requested_language, source_type, url, status,
            caption_language, caption_kind, caption_format, cue_count,
            transcript_sha256, transcript_chars, transcript_text,
            first_processed_at, last_processed_at, attempt_count, last_cache_hit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id, requested_language) DO UPDATE SET
            source_type = excluded.source_type,
            url = excluded.url,
            status = excluded.status,
            caption_language = excluded.caption_language,
            caption_kind = excluded.caption_kind,
            caption_format = excluded.caption_format,
            cue_count = excluded.cue_count,
            transcript_sha256 = excluded.transcript_sha256,
            transcript_chars = excluded.transcript_chars,
            transcript_text = excluded.transcript_text,
            last_processed_at = excluded.last_processed_at,
            attempt_count = excluded.attempt_count,
            last_cache_hit = excluded.last_cache_hit
        """,
        (
            request["video_id"],
            request.get("language", "auto"),
            request["source_type"],
            request["url"],
            result["status"],
            caption.get("language"),
            caption.get("kind"),
            caption.get("format"),
            caption.get("cue_count"),
            result.get("transcript_sha256"),
            int(result.get("transcript_chars") or 0),
            transcript_text,
            first,
            now,
            attempts,
            1 if result.get("cache_hit") is True else 0,
        ),
    )


def export_index(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT video_id, requested_language, source_type, url, status,
               caption_language, caption_kind, caption_format, cue_count,
               transcript_sha256, transcript_chars, first_processed_at,
               last_processed_at, attempt_count, last_cache_hit
        FROM processed
        ORDER BY last_processed_at DESC, video_id, requested_language
        """
    ).fetchall()
    status_counts = {"ok": 0, "skipped_no_captions": 0, "access_blocked": 0, "error": 0}
    unique_videos = set()
    items = []
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        unique_videos.add(row["video_id"])
        item = {
            "video_id": row["video_id"],
            "source_type": row["source_type"],
            "url": row["url"],
            "requested_language": row["requested_language"],
            "status": status,
            "caption": None,
            "transcript_sha256": row["transcript_sha256"],
            "transcript_chars": row["transcript_chars"],
            "first_processed_at": row["first_processed_at"],
            "last_processed_at": row["last_processed_at"],
            "attempt_count": row["attempt_count"],
            "last_cache_hit": bool(row["last_cache_hit"]),
        }
        if status == "ok":
            item["caption"] = {
                "language": row["caption_language"],
                "kind": row["caption_kind"],
                "format": row["caption_format"],
                "cue_count": row["cue_count"],
            }
        items.append(item)

    payload = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "unique_videos": len(unique_videos),
        "processed_entries": len(rows),
        "captions_done": status_counts.get("ok", 0),
        "status_counts": status_counts,
        "items": items,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "processed-index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def finalize() -> int:
    request = load_request()
    result = load_result()
    if "cache_hit" not in result:
        result["cache_hit"] = False
        (RESULTS / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    with connect() as conn:
        upsert_result(conn, request, result)
        payload = export_index(conn)
        conn.commit()
    print(json.dumps({
        "request_id": request["request_id"],
        "cache_hit": bool(result.get("cache_hit")),
        "captions_done": payload["captions_done"],
        "processed_entries": payload["processed_entries"],
    }))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("precheck", "finalize"))
    args = parser.parse_args()
    raise SystemExit(precheck() if args.command == "precheck" else finalize())


if __name__ == "__main__":
    main()
