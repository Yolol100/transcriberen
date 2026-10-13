#!/usr/bin/env python3
"""Fail-closed handoff for a completed 500-video review batch.

This has no transport or dispatch side effects. In particular, a plan alone
cannot authorize the next batch, and the public repository cannot fetch a
private ChatGPT file without a separate authorized private channel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


class ChainError(ValueError):
    pass


HEX = re.compile(r"^[a-f0-9]{64}$")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path: Path, limit: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ChainError("missing, linked or oversized completion evidence")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ChainError("invalid completion evidence JSON") from exc
    if not isinstance(data, dict):
        raise ChainError("completion evidence must be an object")
    return data


def decide(inventory: dict, requested_batch: int, mode: str) -> dict:
    """Pure arithmetic plan; this function alone NEVER proves completion."""
    if not isinstance(inventory, dict) or inventory.get("status") != "inventory_only":
        raise ChainError("trusted inventory-only plan required")
    total = inventory.get("total_unique_videos_in_supplied_corpus")
    actual = inventory.get("actual_batch_count")
    if (type(total) is not int or not 1 <= total <= 25000
            or type(requested_batch) is not int
            or type(actual) is not int or actual <= 0):
        raise ChainError("invalid corpus count or batch")
    count = (total + 499) // 500
    if not 1 <= requested_batch <= count:
        raise ChainError("batch outside corpus")
    wanted = min(500, total - (requested_batch - 1) * 500)
    if actual != wanted:
        raise ChainError("inventory batch count inconsistent with source")
    if mode not in ("all", "batch", "slice", "inventory"):
        raise ChainError("unrecognized review scope")
    following = requested_batch + 1 if mode == "all" and requested_batch < count else None
    return {
        "schema_version": "1.0",
        "corpus_videos": total,
        "current_batch": requested_batch,
        "current_batch_videos": actual,
        "total_batches": count,
        "next_batch": following,
        "terminal": following is None,
        "transport_status": "requires_authorized_nonpublic_zip_handoff",
    }


def verified_advance(
    inventory: dict, requested_batch: int, *, sources: list[Path],
    review_dirs: list[Path], model_path: Path,
    master_routing: Path | None = None, master_sha256: str = "",
    chunk_size: int = 5600,
) -> dict:
    """Verify EVERY reviewed chunk against the original private source bytes.

    Review directories must be privately staged; never fetch untrusted public
    Actions artifacts or publish the verified detail data back into GitHub.
    Return only counters/digests and a next-batch suggestion, never content.
    """
    from knowledge_analysis.corpus import iter_videos
    from knowledge_analysis.routing import (
        apply_master_routing, load_master_routing, verify_pinned_shards,
    )
    from knowledge_analysis.review import (
        STATUS_COMPLETE, STATUS_NO_TRANSCRIPT_COMMENTS, STATUS_SOURCE_WARNING,
        _valid_prior, signature, split_exact,
    )

    plan = decide(inventory, requested_batch, "all")
    if not sources or len(sources) > 99 or not review_dirs or len(review_dirs) > 25:
        raise ChainError("complete private source and slice evidence required")
    if not 500 <= chunk_size <= 9000:
        raise ChainError("invalid chunk size")
    sources = [Path(p) for p in sources]
    model_path = Path(model_path)
    if (model_path.is_symlink() or not model_path.is_file()
            or not model_path.name.endswith(".gguf")):
        raise ChainError("local model weights unavailable for independent hash check")
    model_hash = _file_sha256(model_path)
    if not HEX.fullmatch(model_hash):
        raise ChainError("invalid local model hash")
    if any(p.is_symlink() or not p.is_file() or p.stat().st_size > 1_500_000_000 for p in sources):
        raise ChainError("unavailable or unsafe source ZIP")
    actual_sources = [{"name": p.name, "sha256": _file_sha256(p)} for p in sources]
    if (len({p.name for p in sources}) != len(sources)
            or inventory.get("source_files") != actual_sources
            or inventory.get("master_routing_sha256") != master_sha256):
        raise ChainError("source hashes differ from pinned inventory")
    if bool(master_routing) != bool(master_sha256):
        raise ChainError("master index and pin must be supplied together")
    routing = None
    if master_routing:
        routing = load_master_routing(Path(master_routing), master_sha256)
        verify_pinned_shards(Path(master_routing), sources, len(routing))
    videos = {}
    for src in sources:
        for video in iter_videos(src):
            if routing is not None:
                video = apply_master_routing(video, routing)
            if video.video_id in videos:
                raise ChainError("duplicate source video ID")
            videos[video.video_id] = video
            if len(videos) > 25000:
                raise ChainError("corpus record limit exceeded")
    if routing is not None and set(videos) != set(routing):
        raise ChainError("pinned master IDs missing or duplicated")
    ordered = sorted(videos)
    if len(ordered) != plan["corpus_videos"]:
        raise ChainError("source video count differs from inventory")
    begin = (requested_batch - 1) * 500
    expected_ids = ordered[begin:begin + 500]
    if len(expected_ids) != plan["current_batch_videos"]:
        raise ChainError("batch video IDs differ from inventory")
    seen_ids, seen_slices, chunks_verified, warnings = set(), set(), 0, 0
    reference_slice_size = None
    for root in review_dirs:
        root = Path(root)
        folder = root / "videos"
        if (root.is_symlink() or folder.is_symlink() or not folder.is_dir()
                or not root.is_dir()):
            raise ChainError("private review directory is missing or linked")
        receipt = _read_json(root / "inventory.json", 2_000_000)
        size, index = receipt.get("slice_size"), receipt.get("slice_index")
        if (type(size) is not int or size < 1 or size > 25
                or type(index) is not int or index < 0 or index > 499
                or (reference_slice_size is not None and reference_slice_size != size)
                or index in seen_slices):
            raise ChainError("invalid or duplicate slice evidence")
        reference_slice_size = size
        seen_slices.add(index)
        ids = expected_ids[index * size:(index + 1) * size]
        if (not ids or receipt.get("selected_video_ids") != ids
                or receipt.get("batch") != requested_batch
                or receipt.get("actual_batch_count") != len(expected_ids)
                or receipt.get("total_unique_videos_in_supplied_corpus") != len(ordered)
                or receipt.get("source_files") != actual_sources
                or receipt.get("master_routing_sha256") != master_sha256
                or receipt.get("source_partial") is not False
                or receipt.get("status") != "evidence_only_pending_external_qa"
                or receipt.get("model_sha256") != model_hash
                or receipt.get("scope") != "evidence_only"):
            raise ChainError("slice receipt does not match the verified source")
        statuses = receipt.get("statuses")
        allowed = {STATUS_COMPLETE, STATUS_SOURCE_WARNING, STATUS_NO_TRANSCRIPT_COMMENTS}
        if (not isinstance(statuses, dict) or not statuses
                or any(key not in allowed or type(value) is not int or value < 0
                       for key, value in statuses.items())
                or sum(statuses.values()) != len(ids)):
            raise ChainError("slice reports incomplete model processing")
        if receipt.get("ai_reviewed_videos") != (
            statuses.get(STATUS_COMPLETE, 0) + statuses.get(STATUS_SOURCE_WARNING, 0)
        ):
            raise ChainError("slice model-review counter mismatch")
        files = sorted(folder.iterdir())
        if (len(files) != len(ids)
                or {p.name for p in files} != {video_id + ".json" for video_id in ids}
                or any(p.is_symlink() or not p.is_file() for p in files)):
            raise ChainError("missing, duplicate or extra video review files")
        actual_statuses = {status: 0 for status in allowed}
        for video_id in ids:
            video = videos[video_id]
            review = _read_json(folder / (video_id + ".json"), 16_000_000)
            expected_status = ("no_transcript" if not video.transcript and not video.comments else
                               STATUS_NO_TRANSCRIPT_COMMENTS if not video.transcript else
                               STATUS_SOURCE_WARNING if video.transcript_hash_status != "match" else
                               STATUS_COMPLETE)
            if expected_status == "no_transcript":
                raise ChainError("video has no reviewable source evidence")
            tasks = [("transcript", None, start, end, text)
                     for start, end, text in split_exact(video.transcript, chunk_size)]
            for comment_index, comment in enumerate(video.comments):
                tasks.extend(("comment", comment_index, start, end, text)
                             for start, end, text in split_exact(comment, chunk_size))
            if (review.get("status") != expected_status
                    or review.get("signature") != signature(video, model_hash, chunk_size)
                    or not _valid_prior(review, tasks, expected_status=expected_status,
                                        video=video, model_sha256=model_hash)):
                raise ChainError("incomplete or altered video review: " + video_id)
            actual_statuses[expected_status] += 1
            chunks_verified += len(tasks)
            warnings += expected_status == STATUS_SOURCE_WARNING
            if video_id in seen_ids:
                raise ChainError("duplicate video review across slices")
            seen_ids.add(video_id)
        if {key: value for key, value in actual_statuses.items() if value} != statuses:
            raise ChainError("slice status summary differs from checked reviews")
    wanted_slices = (len(expected_ids) + reference_slice_size - 1) // reference_slice_size
    if seen_slices != set(range(wanted_slices)) or seen_ids != set(expected_ids):
        raise ChainError("batch has missing slices or video IDs")
    plan.update({
        "completion_verified": True,
        "verified_review_videos": len(seen_ids),
        "verified_model_chunks": chunks_verified,
        "source_hash_warning_videos": warnings,
        "model_sha256": model_hash,
        "transport_status": "not_dispatched_requires_private_transport",
    })
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe next-batch plan or checked completion")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--scope", choices=("inventory", "slice", "batch", "all"), required=True)
    parser.add_argument("--source", type=Path, nargs="+", action="append")
    parser.add_argument("--reviews-dir", type=Path, action="append")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--master-routing", type=Path)
    parser.add_argument("--master-sha256", default="")
    parser.add_argument("--chunk-size", type=int, default=5600)
    args = parser.parse_args()
    source_paths = [path for group in (args.source or []) for path in group]
    try:
        inventory = _read_json(args.inventory, 2_000_000)
        if args.scope == "all":
            if not args.model_path or not source_paths or not args.reviews_dir:
                raise ChainError("all-batch continuation requires independently verified private reviews")
            report = verified_advance(
                inventory, args.batch, sources=source_paths,
                review_dirs=args.reviews_dir, model_path=args.model_path,
                master_routing=args.master_routing, master_sha256=args.master_sha256,
                chunk_size=args.chunk_size,
            )
        else:
            report = decide(inventory, args.batch, args.scope)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ChainError, OSError, ValueError) as exc:
        print("BLOCKED: " + str(exc), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())