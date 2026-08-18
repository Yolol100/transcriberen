#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_request_sha256(req):
    encoded = json.dumps(req, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(encoded)


def current_tool_digests():
    root = Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd()))
    candidates = {
        "yt-dlp": root / "tools" / "bin" / "yt-dlp.bin",
        "deno": root / "tools" / "bin" / "deno",
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
    }
    result = {}
    for name, raw_path in candidates.items():
        if raw_path and Path(raw_path).is_file():
            result[name] = sha256_file(raw_path)
    return result


def validate_result(result_path, request_path=None):
    result_path = Path(result_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    results_dir = result_path.parent
    errors = []

    if result.get("schema_version") != "webactueel-transcription-result/1.0": errors.append("schema_version")
    if result.get("owner") != "webactueel-workflow": errors.append("owner")
    if result.get("project_id") != "project-transcriberen": errors.append("project_id")
    if result.get("evidence_level") != "controlled_runtime": errors.append("evidence_level")
    if not HEX64.fullmatch(str(result.get("content_sha256", ""))): errors.append("content_sha256")
    if not isinstance(result.get("content_chars"), int) or result.get("content_chars", -1) < 0: errors.append("content_chars")
    if not result.get("rights_basis"): errors.append("rights_basis")
    if not isinstance(result.get("audio_access_authorized"), bool): errors.append("audio_access_authorized")
    if not result.get("source_context", {}).get("source_set_version"): errors.append("source_context")

    versions = result.get("tool_versions", {})
    for name in ("yt-dlp", "ffmpeg", "ffprobe", "trafilatura"):
        if not versions.get(name): errors.append(f"tool version {name}")

    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance")
        provenance = {}
    if not HEX64.fullmatch(str(provenance.get("request_sha256", ""))): errors.append("provenance request_sha256")
    if not str(provenance.get("repository_commit", "")).strip(): errors.append("provenance repository_commit")
    if not str(provenance.get("python_version", "")).strip(): errors.append("provenance python_version")
    if not str(provenance.get("platform", "")).strip(): errors.append("provenance platform")
    recorded_digests = provenance.get("tool_sha256") if isinstance(provenance.get("tool_sha256"), dict) else {}
    for name in ("yt-dlp", "deno", "ffmpeg", "ffprobe"):
        if not HEX64.fullmatch(str(recorded_digests.get(name, ""))): errors.append(f"provenance tool sha256 {name}")
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true" and os.environ.get("GITHUB_SHA"):
        if provenance.get("repository_commit") != os.environ["GITHUB_SHA"]:
            errors.append("provenance repository_commit mismatch")
    actual_digests = current_tool_digests()
    for name in ("yt-dlp", "deno", "ffmpeg", "ffprobe"):
        if actual_digests.get(name) and recorded_digests.get(name) != actual_digests[name]:
            errors.append(f"provenance current tool digest {name}")

    if request_path is None:
        request_path = os.environ.get("REQUEST_FILE", "resolved-request.json")
    request_path = Path(request_path)
    if request_path.is_file():
        req = json.loads(request_path.read_text(encoding="utf-8"))
        if provenance.get("request_sha256") != canonical_request_sha256(req): errors.append("provenance request_sha256")
        if result.get("request_id") != req.get("request_id"): errors.append("request_id mismatch")
        if result.get("source_url") != req.get("url"): errors.append("source_url mismatch")
        if result.get("requested_mode") != req.get("mode"): errors.append("requested_mode mismatch")
        if result.get("reuse_allowed") is not bool(req.get("reuse_allowed")): errors.append("reuse_allowed mismatch")
        if result.get("rights_basis") != req.get("rights_basis"): errors.append("rights_basis mismatch")
        if result.get("source_context") != req.get("source_context"): errors.append("source_context mismatch")

    if result.get("detected_mode") == "whisper" and not result.get("audio_access_authorized"):
        errors.append("whisper requires authorized audio")
    host = (urlsplit(str(result.get("source_url", ""))).hostname or "").lower().rstrip(".")
    if result.get("detected_mode") == "whisper" and (host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")):
        errors.append("public YouTube may not use whisper")

    content = results_dir / "content.md"
    if result.get("content_persisted"):
        if not content.is_file():
            errors.append("content.md required when content_persisted=true")
        else:
            persisted = content.read_text(encoding="utf-8")
            if sha256_text(persisted) != result.get("content_sha256"): errors.append("persisted content sha256 mismatch")
            if len(persisted) != result.get("content_chars"): errors.append("persisted content chars mismatch")
    elif content.exists():
        errors.append("content.md forbidden when content_persisted=false")

    if result.get("detected_mode") == "youtube_collection":
        metadata = result.get("metadata", {})
        items = metadata.get("items")
        if not isinstance(items, list) or not items:
            errors.append("youtube collection items")
            items = []
        allowed_statuses = {
            "captions_collected", "no_usable_captions", "caption_access_error",
            "processing_error", "not_attempted_source_access_blocked",
        }
        if any(item.get("status") not in allowed_statuses for item in items if isinstance(item, dict)):
            errors.append("youtube collection item status")
        expected_counts = {
            "captions_collected": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "captions_collected"),
            "captions_unavailable": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "no_usable_captions"),
            "caption_access_errors": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "caption_access_error"),
            "processing_errors": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "processing_error"),
            "not_attempted_source_access_blocked": sum(1 for item in items if isinstance(item, dict) and item.get("status") == "not_attempted_source_access_blocked"),
        }
        for key, value in expected_counts.items():
            if metadata.get(key) != value: errors.append(f"youtube collection {key}")
        if metadata.get("attempted_items") != len(items) - expected_counts["not_attempted_source_access_blocked"]:
            errors.append("youtube collection attempted_items")
        if metadata.get("not_attempted_items") != expected_counts["not_attempted_source_access_blocked"]:
            errors.append("youtube collection not_attempted_items")
        discovery_errors = metadata.get("discovery_errors")
        if not isinstance(discovery_errors, list):
            errors.append("youtube collection discovery_errors")
            discovery_errors = []
        expected_discovery_status = "partial" if discovery_errors else "complete"
        if metadata.get("discovery_status") != expected_discovery_status: errors.append("youtube collection discovery_status")
        targets = metadata.get("collection_targets")
        if not isinstance(targets, list) or not targets: errors.append("youtube collection targets")
        attempted_targets = metadata.get("discovery_targets_attempted")
        if not isinstance(attempted_targets, list) or not attempted_targets: errors.append("youtube collection discovery targets attempted")

        if expected_counts["captions_collected"]:
            degraded = expected_counts["caption_access_errors"] or expected_counts["processing_errors"] or expected_counts["not_attempted_source_access_blocked"] or discovery_errors
            expected_scan_status = "partial" if degraded else "captions_collected"
        elif expected_counts["caption_access_errors"] or expected_counts["not_attempted_source_access_blocked"]:
            expected_scan_status = "source_access_blocked"
        elif expected_counts["processing_errors"] or discovery_errors:
            expected_scan_status = "processing_error"
        else:
            expected_scan_status = "no_usable_captions"
        if metadata.get("scan_status") != expected_scan_status: errors.append("youtube collection scan_status")

        expected_persisted = bool(result.get("reuse_allowed")) and expected_counts["captions_collected"] > 0
        if result.get("content_persisted") is not expected_persisted: errors.append("content persistence mismatch")
        if not expected_counts["captions_collected"] and result.get("content_chars") != 0: errors.append("empty collection content_chars")
        if not expected_counts["captions_collected"] and result.get("content_sha256") != sha256_text(""): errors.append("empty collection content_sha256")

        register_path = results_dir / "source-register.json"
        if not register_path.is_file():
            errors.append("source-register.json required for youtube_collection")
        else:
            try:
                register = json.loads(register_path.read_text(encoding="utf-8"))
            except Exception:
                errors.append("source register json")
            else:
                if register.get("schema_version") != "webactueel-source-register/1.0": errors.append("source register schema")
                if register.get("request_id") != result.get("request_id"): errors.append("source register request_id")
                if register.get("sources") != items: errors.append("source register sources")
                if register.get("request_sha256") != provenance.get("request_sha256"): errors.append("source register request_sha256")
                if register.get("repository_commit") != provenance.get("repository_commit"): errors.append("source register repository_commit")

        handoff_path = results_dir / "knowledge-handoff.json"
        if not handoff_path.is_file():
            errors.append("knowledge-handoff.json required for youtube_collection")
        else:
            try:
                handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            except Exception:
                errors.append("knowledge handoff json")
            else:
                if handoff.get("schema_version") != "webactueel-knowledge-handoff/1.0": errors.append("knowledge handoff schema")
                if handoff.get("request_id") != result.get("request_id"): errors.append("knowledge handoff request_id")
                if not result.get("reuse_allowed"):
                    expected_status = "rights_review_required"
                elif expected_counts["captions_collected"]:
                    expected_status = "review_required"
                elif expected_counts["caption_access_errors"] or expected_counts["processing_errors"] or expected_counts["not_attempted_source_access_blocked"] or discovery_errors:
                    expected_status = "source_access_blocked"
                else:
                    expected_status = "no_content"
                if handoff.get("promotion_status") != expected_status: errors.append("knowledge handoff promotion_status")
                expected_available = expected_counts["captions_collected"] > 0
                if handoff.get("content_available") is not expected_available: errors.append("knowledge handoff content_available")
                expected_path = "content.md" if expected_persisted else None
                if handoff.get("content_path") != expected_path: errors.append("knowledge handoff content_path")
                if handoff.get("source_register_path") != "source-register.json": errors.append("knowledge handoff source register")
                if handoff.get("source_items") != items: errors.append("knowledge handoff source_items")
                if handoff.get("request_sha256") != provenance.get("request_sha256"): errors.append("knowledge handoff request_sha256")
                if handoff.get("repository_commit") != provenance.get("repository_commit"): errors.append("knowledge handoff repository_commit")
    else:
        expected_persisted = bool(result.get("reuse_allowed"))
        if result.get("content_persisted") is not expected_persisted: errors.append("content persistence mismatch")

    return errors


def main():
    result_path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/result.json")
    request_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    errors = validate_result(result_path, request_path)
    if errors:
        print("result validation failed: " + ", ".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print("result contract: OK")


if __name__ == "__main__":
    main()
