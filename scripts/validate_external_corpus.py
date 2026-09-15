#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_MEMBERS = 50_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
ALLOWED_TERMINAL_STATUS = {"success", "partial"}
ALLOWED_ITEM_STATUS = {
    "saved",
    "skipped_already_saved",
    "skipped_no_subtitles",
    "skipped_error",
    "skipped_errors",
    "skipped_unavailable",
    "skipped_out_of_range",
    "skipped_unknown_date",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{3,160}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


class IntakeError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntakeError(f"invalid JSON: {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise IntakeError(f"JSON root must be an object: {path.name}")
    return value


def normalize_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise IntakeError(f"unsafe archive member path: {name!r}")
    if candidate.parts and re.match(r"^[A-Za-z]:$", candidate.parts[0]):
        raise IntakeError(f"unsafe archive member drive path: {name!r}")
    return candidate


def validate_zip_metadata(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise IntakeError(f"archive member limit exceeded: {len(infos)}")
            total = 0
            seen: set[str] = set()
            for info in infos:
                member = normalize_member_name(info.filename)
                key = member.as_posix().casefold()
                if key in seen:
                    raise IntakeError(f"duplicate archive member path: {member.as_posix()}")
                seen.add(key)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise IntakeError(f"symlink archive member is not allowed: {member.as_posix()}")
                total += max(0, info.file_size)
                if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise IntakeError("archive uncompressed-size limit exceeded")
    except zipfile.BadZipFile as exc:
        raise IntakeError(f"invalid ZIP archive: {path.name}") from exc


def safe_extract_zip(path: Path, destination: Path) -> None:
    validate_zip_metadata(path)
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            member = normalize_member_name(info.filename)
            target = destination.joinpath(*member.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def locate_payload_root(root: Path) -> Path:
    direct_receipts = list(root.glob("RESULT-RECEIPT_*.json"))
    if direct_receipts:
        return root
    children = [p for p in root.iterdir() if p.is_dir()]
    matches = [p for p in children if list(p.glob("RESULT-RECEIPT_*.json"))]
    if len(matches) != 1:
        raise IntakeError("expected exactly one payload root containing RESULT-RECEIPT_*.json")
    return matches[0]


def locate_receipt(payload_root: Path) -> tuple[Path, dict]:
    canonical = [
        p for p in payload_root.glob("RESULT-RECEIPT_*.json")
        if p.name != "RESULT-RECEIPT_LATEST.json"
    ]
    if len(canonical) != 1:
        raise IntakeError(f"expected one canonical result receipt, found {len(canonical)}")
    receipt_path = canonical[0]
    receipt = read_json(receipt_path)
    run_id = str(receipt.get("run_id", ""))
    if not RUN_ID_RE.fullmatch(run_id):
        raise IntakeError("receipt run_id is missing or unsafe")
    expected_name = f"RESULT-RECEIPT_{run_id}.json"
    if receipt_path.name != expected_name:
        raise IntakeError(f"receipt filename/run_id mismatch: expected {expected_name}")
    latest = payload_root / "RESULT-RECEIPT_LATEST.json"
    if latest.is_file() and read_json(latest) != receipt:
        raise IntakeError("RESULT-RECEIPT_LATEST.json does not match canonical receipt")
    return receipt_path, receipt


def parse_run_sha(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise IntakeError("RUN-SHA256.txt is missing")
    result: dict[str, str] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0].lower()):
            raise IntakeError(f"invalid RUN-SHA256.txt line {line_no}")
        rel = normalize_member_name(parts[1].strip()).as_posix()
        if rel in result:
            raise IntakeError(f"duplicate RUN-SHA256 path: {rel}")
        result[rel] = parts[0].lower()
    if not result:
        raise IntakeError("RUN-SHA256.txt is empty")
    return result


def integer_field(obj: dict, key: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntakeError(f"{key} must be a non-negative integer")
    return value


def verify_manifest_and_receipt(payload_root: Path, receipt: dict) -> tuple[Path, dict]:
    if receipt.get("schema_version") != 1:
        raise IntakeError("unsupported receipt schema_version")
    terminal_status = receipt.get("terminal_status")
    if terminal_status not in ALLOWED_TERMINAL_STATUS:
        raise IntakeError(f"unsupported terminal_status: {terminal_status!r}")
    partial_reasons = receipt.get("partial_reasons", [])
    if not isinstance(partial_reasons, list) or not all(isinstance(v, str) and v for v in partial_reasons):
        raise IntakeError("receipt partial_reasons must be a list of non-empty strings")
    if terminal_status == "partial" and not partial_reasons:
        raise IntakeError("partial receipt must include partial_reasons")
    if terminal_status == "success" and partial_reasons:
        raise IntakeError("success receipt must not include partial_reasons")

    run_id = receipt["run_id"]
    run_dir = payload_root / f"run_{run_id}"
    if not run_dir.is_dir():
        raise IntakeError(f"run directory missing: run_{run_id}")
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise IntakeError("manifest.json is missing")
    manifest_sha = str(receipt.get("manifest_sha256", "")).lower()
    if not SHA256_RE.fullmatch(manifest_sha):
        raise IntakeError("receipt manifest_sha256 is invalid")
    actual_manifest_sha = sha256_file(manifest_path)
    if actual_manifest_sha != manifest_sha:
        raise IntakeError("manifest SHA-256 does not match receipt")

    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 2:
        raise IntakeError("unsupported manifest schema_version")
    if manifest.get("run_id") != run_id:
        raise IntakeError("manifest run_id does not match receipt")
    if manifest.get("version") != receipt.get("version"):
        raise IntakeError("manifest version does not match receipt")
    if manifest.get("run_status") != terminal_status:
        raise IntakeError("manifest run_status does not match receipt")
    for key in ("saved", "discovered"):
        if integer_field(manifest, key) != integer_field(receipt, key):
            raise IntakeError(f"manifest {key} does not match receipt")
    if manifest.get("partial_reasons", []) != partial_reasons:
        raise IntakeError("manifest partial_reasons do not match receipt")
    items = manifest.get("items")
    if not isinstance(items, list):
        raise IntakeError("manifest items must be a list")
    if len(items) != integer_field(receipt, "discovered"):
        raise IntakeError("manifest item count does not match discovered")
    return run_dir, manifest


def verify_result_zip(payload_root: Path, receipt: dict) -> Path:
    name = receipt.get("result_zip")
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith(".zip"):
        raise IntakeError("receipt result_zip must be a simple ZIP filename")
    path = payload_root / name
    if not path.is_file():
        raise IntakeError(f"result ZIP is missing: {name}")
    expected = str(receipt.get("result_zip_sha256", "")).lower()
    if not SHA256_RE.fullmatch(expected):
        raise IntakeError("receipt result_zip_sha256 is invalid")
    if sha256_file(path) != expected:
        raise IntakeError("result ZIP SHA-256 does not match receipt")
    validate_zip_metadata(path)
    return path


def verify_items(run_dir: Path, manifest: dict) -> tuple[list[dict], dict]:
    checksums = parse_run_sha(run_dir / "RUN-SHA256.txt")
    candidate_index: list[dict] = []
    status_counts: Counter[str] = Counter()
    seen_video_ids: set[str] = set()
    saved_count = 0

    for position, item in enumerate(manifest["items"], 1):
        if not isinstance(item, dict):
            raise IntakeError(f"manifest item {position} is not an object")
        video_id = str(item.get("video_id", ""))
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise IntakeError(f"manifest item {position} has invalid video_id")
        if video_id in seen_video_ids:
            raise IntakeError(f"duplicate video_id in manifest: {video_id}")
        seen_video_ids.add(video_id)
        status_value = str(item.get("status", ""))
        if status_value not in ALLOWED_ITEM_STATUS:
            raise IntakeError(f"unsupported item status {status_value!r} for {video_id}")
        status_counts[status_value] += 1

        output_file = item.get("output_file") or ""
        transcript_sha = None
        transcript_bytes = None
        if status_value == "saved":
            saved_count += 1
            if not isinstance(output_file, str) or not output_file:
                raise IntakeError(f"saved item {video_id} has no output_file")
            rel = normalize_member_name(output_file).as_posix()
            if not rel.startswith("items/"):
                raise IntakeError(f"saved item path must be under items/: {rel}")
            transcript_path = run_dir.joinpath(*PurePosixPath(rel).parts)
            if not transcript_path.is_file():
                raise IntakeError(f"saved transcript missing: {rel}")
            expected_sha = checksums.get(rel)
            if expected_sha is None:
                raise IntakeError(f"saved transcript missing from RUN-SHA256.txt: {rel}")
            transcript_sha = sha256_file(transcript_path)
            if transcript_sha != expected_sha:
                raise IntakeError(f"saved transcript SHA-256 mismatch: {rel}")
            transcript_bytes = transcript_path.stat().st_size
        elif output_file:
            raise IntakeError(f"non-saved item {video_id} unexpectedly has output_file")

        candidate_index.append({
            "video_id": video_id,
            "channel": item.get("channel"),
            "category": item.get("category"),
            "type": item.get("type"),
            "title": item.get("title"),
            "upload_date": item.get("upload_date"),
            "url": item.get("url"),
            "status": status_value,
            "reason": item.get("reason") or "",
            "transcript_language": item.get("transcript_language") or "",
            "transcript_kind": item.get("transcript_kind") or "",
            "output_file": output_file,
            "transcript_sha256": transcript_sha,
            "transcript_bytes": transcript_bytes,
        })

    if saved_count != integer_field(manifest, "saved"):
        raise IntakeError("saved item count does not match manifest saved")

    referenced = {entry["output_file"] for entry in candidate_index if entry["status"] == "saved"}
    extra_checksum_items = sorted(path for path in checksums if path.startswith("items/") and path not in referenced)
    if extra_checksum_items:
        raise IntakeError(f"RUN-SHA256 contains unreferenced item files: {extra_checksum_items[0]}")

    return candidate_index, dict(sorted(status_counts.items()))


def validate_external_corpus(source: Path, output_dir: Path) -> dict:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.exists():
        raise IntakeError(f"source does not exist: {source}")
    if source.is_dir() and (source == output_dir or source in output_dir.parents):
        raise IntakeError("output directory cannot be inside the source directory")

    source_sha = None
    cleanup = None
    if source.is_file():
        if source.suffix.lower() != ".zip":
            raise IntakeError("source file must be a ZIP archive")
        source_sha = sha256_file(source)
        cleanup = tempfile.TemporaryDirectory(prefix="external-corpus-")
        root = Path(cleanup.name)
    elif source.is_dir():
        root = source
    else:
        raise IntakeError("source must be a file or directory")

    try:
        if source.is_file():
            safe_extract_zip(source, root)
        payload_root = locate_payload_root(root)
        receipt_path, receipt = locate_receipt(payload_root)
        run_dir, manifest = verify_manifest_and_receipt(payload_root, receipt)
        result_zip = verify_result_zip(payload_root, receipt)
        candidate_index, status_counts = verify_items(run_dir, manifest)

        channels = manifest.get("channels", [])
        if not isinstance(channels, list):
            raise IntakeError("manifest channels must be a list")
        channel_names = []
        for entry in channels:
            if not isinstance(entry, dict) or not isinstance(entry.get("Name"), str) or not entry.get("Name"):
                raise IntakeError("manifest channel entry is invalid")
            channel_names.append(entry["Name"])

        result = {
            "schema_version": "1.0",
            "capability_id": "external-youtube-caption-corpus-intake",
            "knowledge_status": "evidence_only",
            "source": {
                "kind": "zip" if source.is_file() else "directory",
                "name": source.name,
                "sha256": source_sha,
            },
            "collector": {
                "version": receipt.get("version"),
                "run_id": receipt["run_id"],
                "terminal_status": receipt["terminal_status"],
                "exit_code": receipt.get("exit_code"),
                "created_at": receipt.get("created_at"),
            },
            "window": {
                "date_start": manifest.get("date_start"),
                "date_end": manifest.get("date_end"),
            },
            "counts": {
                "discovered": integer_field(receipt, "discovered"),
                "saved": integer_field(receipt, "saved"),
                "status_counts": status_counts,
                "channels": len(channel_names),
            },
            "channels": channel_names,
            "partial_reasons": list(receipt.get("partial_reasons", [])),
            "provenance": {
                "receipt_sha256": sha256_file(receipt_path),
                "manifest_sha256": receipt["manifest_sha256"],
                "result_zip_sha256": receipt["result_zip_sha256"],
                "result_zip_name": result_zip.name,
                "run_sha256_verified": True,
            },
            "promotion": {
                "automatic_project_truth": False,
                "automatic_skill_truth": False,
                "requires_claim_extraction": True,
                "requires_primary_or_official_verification_when_fact_is_changeable": True,
                "requires_owner_acceptance": True,
            },
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "external-corpus-intake.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "candidate-index.json").write_text(
            json.dumps(candidate_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (output_dir / "candidate-index.csv").open("w", encoding="utf-8", newline="") as fh:
            fieldnames = list(candidate_index[0]) if candidate_index else ["video_id"]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(candidate_index)
        return result
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an externally supplied YouTube caption corpus without acquiring network content.")
    parser.add_argument("source", type=Path, help="Outer ZIP package or already-extracted payload directory")
    parser.add_argument("--output-dir", type=Path, default=Path("external-corpus-intake"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_external_corpus(args.source, args.output_dir)
    except IntakeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"external-corpus-intake: FAILED: {exc}")
        raise SystemExit(1)
    if args.json:
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    else:
        print(f"external-corpus-intake: OK ({result['collector']['terminal_status']}, {result['counts']['saved']} saved / {result['counts']['discovered']} discovered)")


if __name__ == "__main__":
    main()
