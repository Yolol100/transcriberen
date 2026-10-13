#!/usr/bin/env python3
"""Manual, evidence-only semantic review of existing YouTube caption archives.

No YouTube requests, user API keys, extra accounts, external inference or project writes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from knowledge_analysis.corpus import CorpusError, iter_videos
from knowledge_analysis.review import LocalModel, review_video, STATUS_COMPLETE, STATUS_SOURCE_WARNING, STATUS_NO_TRANSCRIPT_COMMENTS


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub-hosted, no-key semantic evidence review")
    parser.add_argument("--source", type=Path, required=True, nargs="+", help="Existing local corpus ZIP(s)")
    parser.add_argument("--output-dir", type=Path, default=Path("knowledge-review-results"))
    parser.add_argument("--batch", type=int, default=1, help="1-indexed 500-video logical batch")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--slice", type=int, default=0, help="0-indexed slice within batch")
    parser.add_argument("--slice-size", type=int, default=20)
    parser.add_argument("--mode", choices=("inventory", "review"), default="inventory")
    parser.add_argument("--model-path", type=Path, help="Required in review mode: verified local GGUF model")
    parser.add_argument("--chunk-size", type=int, default=5600)
    parser.add_argument("--time-budget-seconds", type=int, default=10800)
    args = parser.parse_args()
    if not 1 <= args.batch <= 1000 or args.batch_size != 500:
        parser.error("batch must be 1..1000 and batch-size is fixed to 500")
    if not 0 <= args.slice <= 499 or not 1 <= args.slice_size <= 25:
        parser.error("slice must be 0..499; slice-size 1..25")
    if args.chunk_size < 500 or args.chunk_size > 9000:
        parser.error("chunk size must be between 500 and 9000 characters")
    if not 120 <= args.time_budget_seconds <= 18000:
        parser.error("time budget must be between 120 and 18000 seconds")
    if args.mode == "review" and (not args.model_path or not args.model_path.is_file()):
        parser.error("review requires --model-path pointing to a verified local GGUF file")
    for src in args.source:
        if not src.is_file() or src.stat().st_size > 1500 * 1024 * 1024:
            parser.error(f"source missing or too large: {src}")
    all_videos = {}
    for src in args.source:
        for item in iter_videos(src):
            if item.video_id in all_videos:
                prior = all_videos[item.video_id]
                if prior.transcript_sha256 != item.transcript_sha256:
                    raise CorpusError("conflicting duplicate video ID: " + item.video_id)
                raise CorpusError("duplicate video ID across sources: " + item.video_id)
            all_videos[item.video_id] = item
    ordered = [all_videos[key] for key in sorted(all_videos)]
    start = (args.batch - 1) * 500
    end = min(len(ordered), start + 500)
    if start >= len(ordered):
        raise CorpusError("selected batch outside supplied corpus")
    batch = ordered[start:end]
    slice_start = args.slice * args.slice_size
    selected = batch[slice_start:slice_start + args.slice_size]
    if not selected:
        raise CorpusError("selected slice outside selected batch")
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    inventory = {
        "schema_version": "1.0", "scope": "evidence_only",
        "source_files": [{"name": s.name, "sha256": file_hash(s)} for s in args.source],
        "total_unique_videos_in_supplied_corpus": len(ordered), "batch": args.batch,
        "batch_size": 500, "actual_batch_count": len(batch),
        "slice_index": args.slice, "slice_size": args.slice_size,
        "selected_video_ids": [v.video_id for v in selected],
        "status": "inventory_only" if args.mode == "inventory" else "review_running",
    }
    (out / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.mode == "inventory":
        print(json.dumps(inventory, ensure_ascii=False))
        return 0
    model_sha = file_hash(args.model_path)
    client = LocalModel()
    counts = Counter()
    deadline = time.monotonic() + args.time_budget_seconds
    for item in selected:
        if time.monotonic() > deadline:
            counts["not_started_time_budget"] += 1
            continue
        result = review_video(item, model=client, model_sha256=model_sha,
                              out_dir=out, chunk_size=args.chunk_size, deadline=deadline)
        counts[result["status"]] += 1
    inventory.update({
        "status": "evidence_only_pending_external_qa",
        "model_sha256": model_sha, "statuses": dict(counts),
        "ai_reviewed_videos": counts[STATUS_COMPLETE] + counts[STATUS_SOURCE_WARNING],
        "source_integrity_warning_videos": counts[STATUS_SOURCE_WARNING],
        "comments_only_videos": counts[STATUS_NO_TRANSCRIPT_COMMENTS],
        "human_verified_videos": 0,
        "policy_promotions": 0,
    })
    (out / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"batch": args.batch, "slice": args.slice, "counts": dict(counts)}, ensure_ascii=False))
    return 0 if all(k in (STATUS_COMPLETE, STATUS_SOURCE_WARNING, STATUS_NO_TRANSCRIPT_COMMENTS, "no_transcript") for k in counts) else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CorpusError, ValueError) as e:
        print("BLOCKED: " + str(e), file=sys.stderr)
        raise SystemExit(2)