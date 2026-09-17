#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def classify(result_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest_path = result_path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    status = str(result.get("status") or "error")
    reason = "none"
    fallback_required = status == "access_blocked"
    if fallback_required:
        reason = "channel_access_blocked"

    if not fallback_required:
        for item in manifest.get("unresolved") or []:
            if isinstance(item, dict) and item.get("status") == "access_blocked":
                fallback_required = True
                reason = "metadata_access_blocked"
                break

    if not fallback_required:
        for item in manifest.get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("transcript_status") == "access_blocked":
                fallback_required = True
                reason = "caption_access_blocked"
                break
            if item.get("comments_status") == "access_blocked":
                fallback_required = True
                reason = "comments_access_blocked"
                break

    return {
        "status": status,
        "fallback_required": fallback_required,
        "reason": reason,
    }


def main() -> None:
    result_path = Path(sys.argv[1] if len(sys.argv) > 1 else "results/result.json")
    decision = classify(result_path)
    print(json.dumps(decision, separators=(",", ":")))

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"status={decision['status']}\n")
            handle.write(f"fallback_required={'true' if decision['fallback_required'] else 'false'}\n")
            handle.write(f"reason={decision['reason']}\n")


if __name__ == "__main__":
    main()
