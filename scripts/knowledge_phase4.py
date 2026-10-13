#!/usr/bin/env python3
"""Compile phase-4 evidence-only proposals from GitHub-hosted review outputs.

Project/official sources are intentionally not fetched or silently trusted.
Use only local JSON; no API keys, network, user accounts or knowledge writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_analysis.phase4 import Phase4Error, triage


def _read_json(path: Path, max_bytes: int) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise Phase4Error("missing, symlinked or oversized JSON input")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise Phase4Error("invalid JSON input") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline evidence-only phase-4 review ledger")
    parser.add_argument("--reviews-dir", type=Path, required=True, help="Directory with video review JSON files")
    parser.add_argument("--decisions", type=Path, help="Optional offline reviewer proposals (JSON list)")
    parser.add_argument("--out", type=Path, required=True, help="Output evidence-only JSON file")
    args = parser.parse_args()
    if args.reviews_dir.is_symlink() or not args.reviews_dir.is_dir():
        raise Phase4Error("review directory is missing or symlinked")
    paths = sorted(args.reviews_dir.glob("*.json"))
    if not paths or len(paths) > 500:
        raise Phase4Error("expected 1..500 review video JSON files")
    reviews = [_read_json(path, 16_000_000) for path in paths]
    decisions = _read_json(args.decisions, 2_000_000) if args.decisions else None
    if decisions is not None and not isinstance(decisions, list):
        raise Phase4Error("decisions must be an array")
    ledger = triage(reviews, decisions)
    if args.out.exists() or args.out.is_symlink():
        raise Phase4Error("refuse to overwrite existing or linked evidence output")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({key: ledger[key] for key in ("video_records_provided", "claim_count",
          "incomplete_video_records_excluded", "proposed_category_counts", "auto_promoted")},
          sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Phase4Error, OSError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
