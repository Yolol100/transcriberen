#!/usr/bin/env python3
"""Compatibility normalization for extended YouTube runtime fields.

The current result validator intentionally keeps the stable collection/1.1
contract. New retry detail is preserved in additive fields while error-like
comment states are normalized to the existing `error` status before validation.
"""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/youtube-index.json")
index = json.loads(path.read_text(encoding="utf-8"))
items = index.get("items") if isinstance(index.get("items"), list) else []
for item in items:
    if not isinstance(item, dict):
        continue
    status = item.get("comment_status")
    if status in {"access_blocked", "incomplete", "rate_limited"}:
        item["comment_error_kind"] = status
        item["comment_status"] = "error"
index["schema_version"] = "webactueel-youtube-collection/1.1"
index["comment_error_count"] = sum(
    isinstance(item, dict) and item.get("comment_status") == "error" for item in items
)
path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
