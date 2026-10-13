"""Safe read-only ingestion of existing Webactueel and channel caption archives."""
from __future__ import annotations

import bz2
import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath, Path
from typing import Iterator

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_MEMBERS = 35000
MAX_TOTAL_UNCOMPRESSED = 700 * 1024 * 1024
MAX_MEMBER = 80 * 1024 * 1024
MAX_TRANSCRIPT = 2_000_000
MAX_DECOMPRESSED_TEXT = 600 * 1024 * 1024
MAX_RECORDS_PER_ARCHIVE = 25000
MAX_COMMENTS = 250


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel: str
    published_date: str
    url: str
    authority: str
    routes: tuple[str, ...]
    transcript: str
    comments: tuple[str, ...]
    transcript_sha256: str
    comments_status: str
    provenance: str
    transcript_hash_claim: str = ""
    transcript_hash_status: str = "match"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_zip(z: zipfile.ZipFile) -> None:
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS:
        raise CorpusError("too many archive members")
    total = 0
    found = set()
    for info in infos:
        name = info.filename
        posix = PurePosixPath(name)
        if (not name or "\\" in name or name.startswith("/") or
                any(part in ("", ".", "..") for part in name.rstrip("/").split("/")) or
                stat.S_ISLNK(info.external_attr >> 16)):
            raise CorpusError(f"unsafe archive member: {name!r}")
        if name in found:
            raise CorpusError(f"duplicate archive member: {name}")
        found.add(name)
        if info.file_size > MAX_MEMBER:
            raise CorpusError(f"oversized archive member: {name}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise CorpusError("archive exceeds uncompressed budget")


def _routes(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if isinstance(item, str))
    if isinstance(value, str):
        if value.startswith("["):
            import ast
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return _routes(parsed)
            except (ValueError, SyntaxError):
                pass
        return (value,) if value else ()
    return ()


def _comment_texts(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        value = value.get("comments", [])
    if not isinstance(value, list):
        raise CorpusError("invalid comment collection; expected list")
    if len(value) > MAX_COMMENTS:
        raise CorpusError("comment limit exceeded; refuse silent truncation")
    texts = []
    for item in value:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = next((item[k] for k in ("text", "content", "comment", "body")
                         if isinstance(item.get(k), str)), "")
        else:
            raise CorpusError("unreadable comment entry")
        if not isinstance(text, str) or not text.strip():
            raise CorpusError("nontext or empty comment entry")
        if len(text) > 12000:
            raise CorpusError("oversized comment; refuse silent truncation")
        if text.strip():
            texts.append(text.strip())
    return tuple(texts)


def _record_to_video(row: dict, provenance: str) -> Video:
    video_id = str(row.get("video_id") or "")
    if not VIDEO_ID.fullmatch(video_id):
        raise CorpusError(f"invalid video ID in {provenance}")
    transcript = row.get("transcript") or ""
    if not isinstance(transcript, str) or len(transcript.encode("utf-8")) > MAX_TRANSCRIPT:
        raise CorpusError(f"invalid transcript for {video_id}")
    digest = sha256(transcript)
    claimed = row.get("transcript_sha256")
    integrity = "match" if claimed else "missing"
    if claimed and claimed != digest:
        # Legacy Library shard records may carry a digest for the original plain
        # transcript while the inline record includes later timestamped material.
        # Never silently call this a match; do not weaken channel-run validation.
        if row.get("_record_type") == "youtube_video" and row.get("source_member"):
            integrity = "legacy_claim_mismatch"
        else:
            raise CorpusError(f"transcript SHA mismatch for {video_id}")
    comments_raw = row.get("comments", [])
    comments = _comment_texts(comments_raw)
    declared_comment_count = row.get("comment_count")
    if not comments and isinstance(declared_comment_count, int) and declared_comment_count > 0:
        raise CorpusError(f"claimed comments missing in {video_id}")
    status = str(row.get("comments_status") or row.get("comment_parse_status") or "unknown")
    return Video(
        video_id=video_id,
        title=str(row.get("title") or "")[:400],
        channel=str(row.get("channel") or "")[:200],
        published_date=str(row.get("published_date") or row.get("upload_date") or ""),
        url=str(row.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
        authority=str(row.get("source_authority") or "unknown"),
        routes=_routes(row.get("domain_routes")),
        transcript=transcript,
        comments=comments,
        transcript_sha256=digest,
        comments_status=status,
        provenance=provenance,
        transcript_hash_claim=str(claimed or ""),
        transcript_hash_status=integrity,
    )


def _iter_jsonl(fileobj: object, provenance: str) -> Iterator[Video]:
    expanded_bytes = 0
    for number, raw in enumerate(fileobj, start=1):
        expanded_bytes += len(raw)
        if expanded_bytes > MAX_DECOMPRESSED_TEXT or number > MAX_RECORDS_PER_ARCHIVE:
            raise CorpusError(f"expanded corpus exceeds limits at {provenance}:{number}")
        if len(raw) > MAX_TRANSCRIPT * 2:
            raise CorpusError(f"oversized record at {provenance}:{number}")
        row = json.loads(raw)
        if not isinstance(row, dict) or row.get("_record_type", "youtube_video") != "youtube_video":
            continue
        yield _record_to_video(row, f"{provenance}:{number}")


def iter_videos(path: Path) -> Iterator[Video]:
    """Supports shard .zip/.jsonl.bz2 and produced channel-corpus.zip files.

    Archives are inspected in memory, never extracted or executed.
    """
    path = Path(path)
    if path.name.endswith(".jsonl.bz2"):
        with bz2.open(path, "rb") as stream:
            yield from _iter_jsonl(stream, path.name)
        return
    if path.suffix == ".jsonl":
        with path.open("rb") as stream:
            yield from _iter_jsonl(stream, path.name)
        return
    if path.suffix != ".zip":
        raise CorpusError("expected an existing .zip, .jsonl or .jsonl.bz2 source")
    with zipfile.ZipFile(path) as archive:
        _safe_zip(archive)
        names = set(archive.namelist())
        shards = sorted(n for n in names if n.endswith(".jsonl.bz2") or n.endswith(".jsonl"))
        if shards:
            for name in shards:
                with archive.open(name) as fp:
                    if name.endswith(".bz2"):
                        with bz2.BZ2File(fp) as stream:
                            yield from _iter_jsonl(stream, path.name+"/"+name)
                    else:
                        yield from _iter_jsonl(fp, path.name+"/"+name)
            return
        if "manifest.json" not in names:
            raise CorpusError("not a shard or channel-corpus ZIP: manifest missing")
        manifest = json.loads(archive.read("manifest.json"))
        items = manifest.get("items", [])
        if not isinstance(items, list):
            raise CorpusError("invalid manifest items")
        for item in items:
            if not isinstance(item, dict):
                raise CorpusError("non-object manifest item")
            video_id = str(item.get("video_id") or "")
            if not VIDEO_ID.fullmatch(video_id):
                raise CorpusError("invalid video ID in channel manifest")
            base = f"videos/{video_id}"
            metadata_path = f"{base}/metadata.json"
            comments_path = f"{base}/comments.json"
            if metadata_path not in names or comments_path not in names:
                raise CorpusError(f"missing channel metadata/comments: {video_id}")
            metadata = json.loads(archive.read(metadata_path))
            if metadata != item:
                raise CorpusError(f"channel metadata differs from manifest: {video_id}")
            transcript_path = f"{base}/transcript.txt"
            transcript = archive.read(transcript_path).decode("utf-8") if transcript_path in names else ""
            if item.get("transcript_status") == "ok" and not transcript:
                raise CorpusError(f"claimed ok transcript not present: {video_id}")
            if item.get("transcript_status") != "ok" and transcript_path in names:
                raise CorpusError(f"unexpected transcript for non-ok: {video_id}")
            comments = json.loads(archive.read(comments_path))
            row = dict(item)
            row["transcript"] = transcript
            row["comments"] = comments
            row["comments_status"] = comments.get("status", "unknown")
            yield _record_to_video(row, f"{path.name}/{base}")


def source_receipt(path: Path) -> dict:
    """Source completeness metadata, without making any promotion claims."""
    path = Path(path)
    if path.suffix != ".zip":
        return {"kind": "local_jsonl", "status": "evidence_only", "unresolved_count": 0}
    with zipfile.ZipFile(path) as z:
        _safe_zip(z)
        names = set(z.namelist())
        if "manifest.json" not in names:
            return {"kind": "legacy_library_shard", "status": "historical_evidence_only", "unresolved_count": 0}
        manifest = json.loads(z.read("manifest.json"))
        result = json.loads(z.read("result.json")) if "result.json" in names else {}
        unresolved = manifest.get("unresolved", [])
        if not isinstance(unresolved, list):
            raise CorpusError("unresolved source metadata is malformed")
        reasons = manifest.get("partial_reasons", [])
        if not isinstance(reasons, list):
            raise CorpusError("partial reasons metadata is malformed")
        status = str(result.get("status") or manifest.get("status") or "unknown")
        return {
            "kind": "channel_corpus", "status": status,
            "unresolved_count": len(unresolved),
            "partial_reasons": [str(v)[:200] for v in reasons[:100]],
            "counts": manifest.get("counts", {}) if isinstance(manifest.get("counts", {}), dict) else {},
            "source_partial": status != "ok" or bool(unresolved) or bool(reasons),
        }