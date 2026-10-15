#!/usr/bin/env python3
"""Audit a supplied Library YouTube index and all shards without network access.

This is 100% local record inspection, never a claim that all live YouTube
comments are available, fetched, or reviewed. Do not commit generated results
from a private corpus to the public repository.
"""
from __future__ import annotations

import argparse
import bz2
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


class AuditError(ValueError):
    pass


MAX_MASTER_BYTES = 32 * 1024 * 1024
MAX_SHARD_BYTES = 128 * 1024 * 1024
MAX_JSONL_ROW_BYTES = 8 * 1024 * 1024
MAX_SHARD_UNCOMPRESSED_TEXT_BYTES = 700 * 1024 * 1024
MAX_VIDEO_IDS = 25000


def valid_comment(item: object) -> bool:
    if isinstance(item, str):
        value = item
    elif isinstance(item, dict):
        value = next((item[key] for key in ('text', 'content', 'comment', 'body')
                      if isinstance(item.get(key), str)), '')
    else:
        return False
    return bool(value.strip()) and len(value) <= 12000


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_inventory(master: Path):
    if master.stat().st_size > MAX_MASTER_BYTES:
        raise AuditError('master archive exceeds safety limit')
    with zipfile.ZipFile(master) as z:
        if len(z.infolist()) > 100 or any(i.file_size > MAX_MASTER_BYTES for i in z.infolist()):
            raise AuditError('master archive contains oversized members')
        shard_index = json.loads(z.read("YouTube_Kennisbron_Shards_2026-10-03.json"))
        video_rows = list(csv.DictReader(io.StringIO(
            z.read("YouTube_Video_Routing_Index_2026-10-03.csv").decode("utf-8-sig"))))
        catalog = json.loads(z.read("YouTube_Source_Catalog_2026-10-03.json"))
    return shard_index, video_rows, catalog["channels"]


def records(shard: Path):
    if shard.stat().st_size > MAX_SHARD_BYTES:
        raise AuditError(f'oversized shard archive: {shard.name}')
    with zipfile.ZipFile(shard) as z:
        if len(z.infolist()) > 10 or any(i.file_size > MAX_SHARD_BYTES for i in z.infolist()):
            raise AuditError(f'oversized shard ZIP member: {shard.name}')
        corrupt = z.testzip()
        if corrupt:
            raise AuditError(f"ZIP CRC failed: {shard.name}:{corrupt}")
        members = [m for m in z.namelist()
                   if m.endswith((".jsonl.bz2", ".jsonl"))]
        if len(members) != 1:
            raise AuditError(f"expected exactly one JSONL member: {shard.name}")
        member = members[0]
        with z.open(member) as raw:
            stream = bz2.BZ2File(raw) if member.endswith(".bz2") else raw
            with stream:
                expanded = 0
                for line in stream:
                    expanded += len(line)
                    if expanded > MAX_SHARD_UNCOMPRESSED_TEXT_BYTES or len(line) > MAX_JSONL_ROW_BYTES:
                        raise AuditError(f'expanded shard exceeds safety limit: {shard.name}')
                    item = json.loads(line)
                    if item.get("_record_type") == "youtube_video":
                        yield item


def audit(master: Path, shard_dir: Path, output_dir: Path, *,
          expected_master_sha256: str | None = None) -> dict:
    if not master.is_file():
        raise AuditError("master ZIP missing")
    master_sha256 = digest(master)
    if expected_master_sha256 and master_sha256 != expected_master_sha256:
        raise AuditError('master checksum mismatch')
    index, routes, catalog = load_inventory(master)
    expected = {}
    for row in routes:
        video_id = row.get("video_id", "")
        if not video_id or video_id in expected:
            raise AuditError("empty/duplicate video ID in master routing")
        expected[video_id] = row
    parts = index.get("parts", [])
    if len(expected) > MAX_VIDEO_IDS or len(parts) > 100:
        raise AuditError('indexed corpus exceeds safety limits')
    if not parts:
        raise AuditError("master lists no shards")
    seen = set()
    rows = []
    stored_comments = 0
    videos_with_comments = 0
    videos_with_transcript = 0
    shard_results = []
    for part in parts:
        filename = part["filename"]
        if Path(filename).name != filename or not filename.endswith(".zip"):
            raise AuditError(f"unsafe shard filename: {filename}")
        path = shard_dir / filename
        if not path.is_file():
            raise AuditError(f"missing required shard: {filename}")
        actual_hash = digest(path)
        if actual_hash != part.get("zip_sha256"):
            raise AuditError(f"shard checksum mismatch: {filename}")
        count = 0
        for item in records(path):
            count += 1
            video_id = item.get("video_id")
            if video_id in seen:
                raise AuditError(f"duplicate video ID across shards: {video_id}")
            seen.add(video_id)
            row = expected.get(video_id)
            if row is None:
                raise AuditError(f"video absent from master routing: {video_id}")
            comments = item.get("comments") or []
            if not isinstance(comments, list):
                raise AuditError(f"malformed saved comments for {video_id}")
            if any(not valid_comment(comment) for comment in comments):
                raise AuditError(f'empty/invalid saved comment text for {video_id}')
            count_comments = len(comments)
            if int(row.get("comment_count") or "0") != count_comments:
                raise AuditError(f"indexed comment count differs from source: {video_id}")
            videos_with_comments += bool(count_comments)
            stored_comments += count_comments
            has_transcript = bool((item.get("transcript") or "").strip())
            videos_with_transcript += has_transcript
            channel = item.get("channel") or ""
            if channel not in catalog:
                raise AuditError(f"channel absent from current source catalog: {channel}")
            channel_meta = catalog[channel]
            authority = ("verified" if channel_meta.get("authority_status") == "verified"
                         else "unverified_supplemental")
            rows.append({
                "video_id": video_id, "channel": channel,
                "domain_routes": row.get("domain_routes") or "",
                "authority_status": authority,
                "transcript_stored": str(has_transcript).lower(),
                "comments_stored_count": count_comments,
                "comment_evidence_status": ("stored_top_level_comments" if count_comments
                                            else "not_stored"),
                "live_comment_availability": "not_checked",
                "live_comment_retrieval": "not_attempted",
                "saved_comment_text_integrity": "PASS",
                "semantic_comment_usefulness": "not_reviewed",
                "source_shard": filename,
            })
        if count != int(part.get("record_count", -1)):
            raise AuditError(f"shard record count mismatch: {filename}")
        shard_results.append({"name": filename, "sha256": actual_hash,
                              "records": count, "crc": "PASS"})
    if len(seen) != len(expected) or set(expected) != seen:
        raise AuditError("master index and shard video-ID sets are not identical")
    if len(seen) != int(index.get("record_count_total", -1)):
        raise AuditError("master declared total differs from inspected records")
    summary = {
        "schema_version": "1.0", "scope": "local_evidence_only",
        "master_sha256": master_sha256,
        "inspected_videos": len(seen), "index_coverage_pct": 100.0,
        "shards_verified": len(shard_results),
        "videos_with_transcript": videos_with_transcript,
        "videos_with_saved_top_level_comments": videos_with_comments,
        "videos_without_saved_top_level_comments": len(seen) - videos_with_comments,
        "stored_top_level_comments": stored_comments,
        "stored_comment_video_coverage_pct": round(
            100 * videos_with_comments / len(seen), 2),
        "live_youtube_comment_coverage_pct": None,
        "live_youtube_comment_check_status": "not_attempted",
        "live_youtube_comment_check_reason":
            "No authorized live provider was used; absence from stored ZIP is not comments_disabled.",
        "shards": shard_results, "independent_qa": "not_performed",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "video_coverage.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "coverage_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--master", required=True, type=Path)
    p.add_argument("--shard-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--expected-master-sha256", help="Optional exact authoritative master digest")
    args = p.parse_args()
    try:
        summary = audit(args.master, args.shard_dir, args.output_dir,
                        expected_master_sha256=args.expected_master_sha256)
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError,
            TypeError, AuditError, ValueError) as exc:
        p.exit(2, f"BLOCKED_INCOMPLETE: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
