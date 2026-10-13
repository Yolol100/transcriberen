"""SHA-pinned master metadata for historical YouTube shard review.

Only metadata is read. Transcript/comment evidence remains in the original shards.
"""
from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from .corpus import CorpusError, VIDEO_ID, Video, _safe_zip

INDEX_NAME = re.compile(r"^YouTube_Video_Routing_Index_[0-9]{4}-[0-9]{2}-[0-9]{2}\.csv$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
ROUTE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
REQUIRED_COLUMNS = {
    "video_id", "channel", "title", "date", "domain_routes",
    "source_authority", "authority_status", "comment_count",
}
ALLOWED_AUTHORITY = {"", "official_channel", "expert_creator", "research_publisher"}
ALLOWED_STATUS = {"verified", "unverified_supplemental"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _date_key(value: str) -> str:
    if not value:
        return ""
    if re.fullmatch(r"[0-9]{8}", value):
        return value
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return value.replace("-", "")
    raise CorpusError("invalid master routing date")


def load_master_routing(path: Path, expected_sha256: str) -> dict[str, dict]:
    """Read an explicitly authorized master ZIP; never trust a filename alone."""
    path = Path(path)
    if not DIGEST.fullmatch(expected_sha256):
        raise CorpusError("a 64-digit pinned master SHA-256 is required")
    if not path.is_file() or path.stat().st_size > 30_000_000:
        raise CorpusError("master routing ZIP missing or oversized")
    if sha256_file(path) != expected_sha256:
        raise CorpusError("master routing ZIP SHA-256 mismatch")
    try:
        with zipfile.ZipFile(path) as archive:
            _safe_zip(archive)
            matches = [i for i in archive.infolist() if INDEX_NAME.fullmatch(i.filename)]
            if len(matches) != 1:
                raise CorpusError("master must contain exactly one video routing index")
            if matches[0].file_size > 12_000_000:
                raise CorpusError("master routing CSV exceeds limit")
            data = archive.read(matches[0]).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeError, OSError) as exc:
        raise CorpusError("unreadable master routing ZIP") from exc

    reader = csv.DictReader(io.StringIO(data, newline=""))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise CorpusError("master routing index missing required columns")
    result: dict[str, dict] = {}
    try:
        for row in reader:
            if not isinstance(row, dict) or None in row:
                raise CorpusError("malformed master routing CSV row")
            video_id = row.get("video_id", "")
            if not VIDEO_ID.fullmatch(video_id) or video_id in result:
                raise CorpusError("duplicate or invalid video ID in master routing index")
            title, channel = row.get("title", ""), row.get("channel", "")
            if not title or not channel or len(title) > 400 or len(channel) > 200:
                raise CorpusError("invalid master title or channel")
            date = row.get("date", "")
            _date_key(date)
            raw_routes = row.get("domain_routes", "")
            routes = raw_routes.split("|") if raw_routes else []
            if (len(routes) > 20 or len(set(routes)) != len(routes)
                    or any(not ROUTE.fullmatch(v) for v in routes)):
                raise CorpusError("invalid master domain routes")
            authority, status = row.get("source_authority", ""), row.get("authority_status", "")
            if authority not in ALLOWED_AUTHORITY or status not in ALLOWED_STATUS:
                raise CorpusError("invalid master authority status")
            comment_count = row.get("comment_count", "")
            if not comment_count.isdecimal() or int(comment_count) > 250:
                raise CorpusError("invalid master comment count")
            result[video_id] = {
                "title": title, "channel": channel, "date": date,
                "routes": tuple(routes), "authority": authority or status,
                "comment_count": int(comment_count),
            }
            if len(result) > 25_000:
                raise CorpusError("master routing record count exceeds limit")
    except csv.Error as exc:
        raise CorpusError("malformed master routing CSV") from exc
    if not result:
        raise CorpusError("master routing index is empty")
    return result


def apply_master_routing(video: Video, routing: dict[str, dict]) -> Video:
    """Refuse unknown IDs/conflicts; override only classification/date metadata."""
    meta = routing.get(video.video_id)
    if meta is None:
        raise CorpusError("video absent from pinned master routing index: " + video.video_id)
    if meta["title"] != video.title or meta["channel"] != video.channel:
        raise CorpusError("master routing identity mismatch: " + video.video_id)
    if video.published_date and meta["date"] and (
            _date_key(video.published_date) != _date_key(meta["date"])):
        raise CorpusError("master routing date mismatch: " + video.video_id)
    if meta["comment_count"] != len(video.comments):
        raise CorpusError("master routing comment count mismatch: " + video.video_id)
    return replace(video, routes=meta["routes"], authority=meta["authority"],
                   published_date=meta["date"] or video.published_date)


SHARD_MANIFEST_NAME = re.compile(r"^YouTube_Kennisbron_Shards_[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$")
SHARD_ZIP_NAME = re.compile(r"^YouTube_Kennisbron_Master\.part-[0-9]{2}\.zip$")


def verify_pinned_shards(master_path: Path, source_paths: list[Path], expected_video_count: int) -> None:
    """Pin every historical shard to the exact manifest contained in the master.

    SHA/size and complete-file-set checks precede any transcript parsing/model call.
    """
    try:
        with zipfile.ZipFile(master_path) as archive:
            _safe_zip(archive)
            matches = [entry for entry in archive.infolist()
                       if SHARD_MANIFEST_NAME.fullmatch(entry.filename)]
            if len(matches) != 1 or matches[0].file_size > 2_000_000:
                raise CorpusError("master requires one bounded shard manifest")
            manifest = json.loads(archive.read(matches[0]))
    except (zipfile.BadZipFile, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusError("unreadable master shard manifest") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("parts"), list):
        raise CorpusError("invalid master shard manifest")
    parts = manifest["parts"]
    if not 1 <= len(parts) <= 99 or manifest.get("record_count_total") != expected_video_count:
        raise CorpusError("master shard count or video total mismatch")
    expected: dict[str, tuple[int, str]] = {}
    records_total = 0
    for part_no, row in enumerate(parts, start=1):
        if not isinstance(row, dict):
            raise CorpusError("invalid master shard entry")
        name = row.get("filename")
        digest = row.get("zip_sha256")
        size = row.get("zip_size_bytes")
        count = row.get("record_count")
        if (row.get("part") != part_no
                or not isinstance(name, str)
                or not SHARD_ZIP_NAME.fullmatch(name)
                or name != f"YouTube_Kennisbron_Master.part-{part_no:02d}.zip"
                or not isinstance(digest, str) or not DIGEST.fullmatch(digest)
                or not isinstance(size, int) or not 1 <= size <= 1_500_000_000
                or not isinstance(count, int) or not 1 <= count <= 25_000):
            raise CorpusError("invalid master shard metadata")
        if name in expected:
            raise CorpusError("duplicate shard in master manifest")
        expected[name] = (size, digest)
        records_total += count
    if records_total != expected_video_count:
        raise CorpusError("master shard record count does not match index")
    paths = [Path(path) for path in source_paths]
    provided = {path.name: path for path in paths}
    if len(provided) != len(paths) or set(provided) != set(expected):
        raise CorpusError("supplied historical shard set differs from pinned master")
    for name, (size, digest) in expected.items():
        path = provided[name]
        if not path.is_file() or path.stat().st_size != size:
            raise CorpusError("pinned shard missing or wrong size: " + name)
        if sha256_file(path) != digest:
            raise CorpusError("pinned shard ZIP SHA-256 mismatch: " + name)
