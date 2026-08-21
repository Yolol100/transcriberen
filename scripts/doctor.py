#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "toolkit-contract.json",
    "scripts/resolve_request.py",
    "scripts/captions_runtime.py",
    "scripts/validate_result.py",
    "scripts/install_tools.sh",
    "scripts/run_local.sh",
    ".github/workflows/transcribe.yml",
    "README.md",
    "SECURITY.md",
    "THREAT-MODEL.md",
}
FORBIDDEN = {
    "scripts/runtime.py",
    "scripts/runtime_topic_filter.py",
    "scripts/youtube_runtime.py",
    "scripts/innertube_runtime.py",
    "scripts/caption_client_profiles.py",
    "scripts/normalize_youtube_result_v2.py",
    "scripts/resolve_request_hardened.py",
    "scripts/install_python_deps.sh",
    ".github/workflows/transcribe-self-hosted.yml",
    ".github/workflows/lock-audit.yml",
    "requirements.in",
    "requirements.txt",
    "requirements.lock",
}
FORBIDDEN_RUNTIME_TERMS = {
    "include_comments",
    "comment_sort",
    "knowledge_context",
    "channel_all",
    "channel_streams",
    "include_keywords",
    "whisper",
    "ffmpeg",
    "trafilatura",
}


def run_checks(root: Path = ROOT) -> dict:
    failures = []
    for relative in sorted(REQUIRED):
        if not (root / relative).is_file():
            failures.append(f"missing required file: {relative}")
    for relative in sorted(FORBIDDEN):
        if (root / relative).exists():
            failures.append(f"obsolete file still present: {relative}")

    contract_path = root / "toolkit-contract.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("source_set_version") != "2.2.0-captions-only":
            failures.append("toolkit source_set_version is not captions-only")
        if contract.get("runtime_target") != "self-hosted-or-local-direct-network":
            failures.append("runtime target must be self-hosted/local direct network")
        ids = {tool.get("id") for tool in contract.get("tools", [])}
        if ids != {"yt-dlp", "deno-ejs-runtime"}:
            failures.append(f"unexpected tool set: {sorted(ids)}")

    for relative in ("scripts/resolve_request.py", "scripts/captions_runtime.py", ".github/workflows/transcribe.yml"):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for term in FORBIDDEN_RUNTIME_TERMS:
            if term in text:
                failures.append(f"obsolete runtime term {term!r} remains in {relative}")

    workflow = root / ".github/workflows/transcribe.yml"
    if workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        if "runs-on: [self-hosted, linux, x64, webactueel-transcribe]" not in text:
            failures.append("transcribe workflow is not bound to dedicated self-hosted runner")
        if "branches: [runtime-requests]" not in text:
            failures.append("transcribe workflow must use runtime-requests branch")

    return {"ok": not failures, "failures": failures, "required_count": len(REQUIRED), "forbidden_count": len(FORBIDDEN)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="local")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_checks()
    if args.json:
        print(json.dumps({"mode": args.mode, **result}, indent=2))
    else:
        print("repository-doctor: OK" if result["ok"] else "repository-doctor: FAILED")
        for failure in result["failures"]:
            print(f"- {failure}")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
