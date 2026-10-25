#!/usr/bin/env python3
"""Offline, read-only input audit of CSV exports from the historic Excel analysis.

No YouTube access, external model, live source writes or knowledge promotion.
The report contains review pointers, not verified methods or corrected dates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from knowledge_analysis.excel_quality import (
    compare_date_flags, inspect_mentions, read_csv_rows, review_counts,
)


def _write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private evidence-only CSV review; never modifies source files")
    parser.add_argument("--mentions-csv", type=Path, help="CSV export of Excel tab 'Bronvermeldingen'")
    parser.add_argument("--excel-index-csv", type=Path, help="CSV export of Excel tab 'Video index'")
    parser.add_argument("--raw-screening-csv", type=Path, help="Private corpus-wide video_screening.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="A new empty directory outside the public repo")
    args = parser.parse_args(argv)
    if not args.mentions_csv and not args.excel_index_csv:
        parser.error("At least one review input is required")
    if bool(args.excel_index_csv) != bool(args.raw_screening_csv):
        parser.error("Date reconciliation requires both Excel index and raw scan exports")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error("Output directory must not already exist (no clobbering)")

    summary = {"schema_version": "1.0", "decision": "EVIDENCE_ONLY_NO_AUTO_PROMOTION",
               "date_policy": "NO_AUTOMATIC_DATE_CORRECTION", "inputs": {}}
    outputs: list[tuple[str, list[dict[str, str]], list[str]]] = []
    # Refuse inputs outside the same bounded safety policy before hashing.
    rows_by_key = {}
    for key, path in [("mentions", args.mentions_csv), ("excel_index", args.excel_index_csv),
                      ("raw_screening", args.raw_screening_csv)]:
        if path:
            rows_by_key[key] = read_csv_rows(path)
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            summary["inputs"][key] = {"sha256": digest.hexdigest()}
    if args.mentions_csv:
        rows = rows_by_key["mentions"]
        records = inspect_mentions(rows)
        summary["mention_rows"] = len(rows)
        summary["reviewed_ambiguous_matches"] = len(records)
        summary["entity_gates"] = review_counts(records)
        outputs.append(("entity_reviews.csv", records,
                        ["video_id", "canonical_entity", "gate", "reason", "auto_promoted"]))
    if args.excel_index_csv:
        excel = rows_by_key["excel_index"]
        raw = rows_by_key["raw_screening"]
        conflicts = compare_date_flags(excel, raw)
        summary["indexed_videos"] = len(excel)
        summary["raw_videos"] = len(raw)
        summary["date_flag_conflicts"] = len(conflicts)
        outputs.append(("date_flag_conflicts.csv", conflicts,
                        ["video_id", "excel_exact", "raw_exact", "excel_date", "raw_date", "review"]))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, records, columns in outputs:
        _write_csv(args.output_dir / name, records, columns)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False,
                                                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "inputs"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
