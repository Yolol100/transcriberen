#!/usr/bin/env python3
"""Choose the next 500-video batch after a successful checked review run.

This is only orchestration of an ALREADY ACCESSIBLE, SHA-pinned source.
It cannot move a ZIP from ChatGPT or make a public release private.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


class ChainError(ValueError):
    pass


def decide(inventory: dict, requested_batch: int, mode: str) -> dict:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-secret next-batch decision")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--scope", choices=("inventory", "slice", "batch", "all"), required=True)
    args = parser.parse_args()
    if args.inventory.is_symlink() or args.inventory.stat().st_size > 2_000_000:
        raise ChainError("unsafe inventory receipt")
    report = decide(json.loads(args.inventory.read_text(encoding="utf-8")),
                    args.batch, args.scope)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ChainError, OSError, ValueError) as err:
        print("BLOCKED: " + str(err), file=__import__("sys").stderr)
        raise SystemExit(2)
