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
    "scripts/channel_runtime.py",
    "scripts/cache_runtime.py",
    "scripts/validate_result.py",
    "scripts/install_tools.sh",
    "scripts/run_local.sh",
    ".github/workflows/transcribe.yml",
    "README.md",
    "SECURITY.md",
    "THREAT-MODEL.md",
    "AGENTS.md",
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
PROJECT_TRUTH_KEYS = {"owner_skill", "owner_mode", "project_id", "source_set_version"}
PROJECT_TRUTH_MARKERS = {"project-transcriberen", "2.2.0-captions-only"}
YT_DLP_VERSION = "2026.08.20.234504"
YT_DLP_SHA256 = "8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93"
DENO_VERSION = "2.9.5"
DENO_SHA256 = "8b010a3b1a4a0188a67cdb8a7a27348b2a501af78aec7fc74f2ace167368d530"
FIXED_POLICY = {
    "year": 2026,
    "max_videos": 1000,
    "comments_per_video": 7,
    "comment_sort": "top",
    "include_replies": False,
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
        if contract.get("schema_version") != "3.0":
            failures.append("toolkit schema_version must be 3.0")
        if contract.get("capability_id") != "public-youtube-channel-caption-corpus":
            failures.append("toolkit capability_id mismatch")
        if contract.get("runtime_target") != "self-hosted-or-local-direct-network":
            failures.append("runtime target must be self-hosted/local direct network")
        if contract.get("inputs") != ["youtube-channel-url", "optional-language"]:
            failures.append("toolkit must expose only channel input plus optional language")
        if contract.get("fixed_policy") != FIXED_POLICY:
            failures.append("fixed channel policy mismatch")
        leaked_keys = sorted(PROJECT_TRUTH_KEYS.intersection(contract))
        if leaked_keys:
            failures.append("project truth keys in toolkit contract: " + ", ".join(leaked_keys))
        tools = {tool.get("id"): tool for tool in contract.get("tools", [])}
        if set(tools) != {"yt-dlp", "deno-ejs-runtime"}:
            failures.append(f"unexpected tool set: {sorted(tools)}")
        else:
            if tools["yt-dlp"].get("version") != YT_DLP_VERSION or tools["yt-dlp"].get("sha256") != YT_DLP_SHA256:
                failures.append("yt-dlp version/hash pin mismatch")
            if tools["deno-ejs-runtime"].get("version") != DENO_VERSION or tools["deno-ejs-runtime"].get("sha256") != DENO_SHA256:
                failures.append("Deno version/hash pin mismatch")

    runtime_files = (
        "toolkit-contract.json",
        "scripts/resolve_request.py",
        "scripts/captions_runtime.py",
        "scripts/channel_runtime.py",
        "scripts/cache_runtime.py",
        "scripts/validate_result.py",
    )
    for relative in runtime_files:
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for marker in PROJECT_TRUTH_MARKERS:
            if marker in text:
                failures.append(f"project truth marker {marker!r} remains in {relative}")

    resolver = root / "scripts/resolve_request.py"
    if resolver.is_file():
        text = resolver.read_text(encoding="utf-8")
        for needle, message in (
            ('ALLOWED_INPUT_KEYS = {"enabled", "request_id", "url", "language"}', "request contract changed unexpectedly"),
            ('"source_type": "channel"', "resolver is not channel-only"),
            ('"year": YEAR', "resolver does not bind year 2026"),
            ('"max_videos": MAX_VIDEOS', "resolver does not bind max_videos"),
            ('"comments_per_video": COMMENTS_PER_VIDEO', "resolver does not bind comment limit"),
            ('"include_replies": False', "resolver does not disable replies"),
        ):
            if needle not in text:
                failures.append(message)

    engine = root / "scripts/captions_runtime.py"
    if engine.is_file():
        text = engine.read_text(encoding="utf-8")
        for needle, message in (
            ('"--skip-download"', "caption engine may download media"),
            ('"--no-cookies"', "caption engine cookie boundary missing"),
            ('comment_sort=top', "YouTube comment top-sort missing"),
            ('max_comments={limit},{limit},0,0,0', "comment parent/reply limits missing"),
        ):
            if needle not in text:
                failures.append(message)
        if 'if __name__ == "__main__"' in text:
            failures.append("caption engine must not remain a standalone single-video CLI")
        if '"--no-warnings"' in text:
            failures.append("yt-dlp warnings must remain visible for access-block classification")

    channel = root / "scripts/channel_runtime.py"
    if channel.is_file():
        text = channel.read_text(encoding="utf-8")
        for needle, message in (
            ('"--playlist-end", str(max_videos)', "channel discovery is not bounded"),
            ('upload_date.startswith("2026")', "exact 2026 filtering missing"),
            ('load_top_comments', "per-video comments are not acquired"),
            ('channel-corpus.zip', "channel ZIP output missing"),
        ):
            if needle not in text:
                failures.append(message)

    cache = root / "scripts/cache_runtime.py"
    if cache.is_file():
        text = cache.read_text(encoding="utf-8")
        for needle, message in (
            ("history.sqlite3", "persistent cache database is not configured"),
            ("PRIMARY KEY (video_id, requested_language)", "cache does not deduplicate by video/language"),
            ("transcript_sha256", "cache transcript-integrity evidence missing"),
        ):
            if needle not in text:
                failures.append(message)

    installer = root / "scripts/install_tools.sh"
    if installer.is_file():
        text = installer.read_text(encoding="utf-8")
        for needle, message in (
            (f'YT_DLP_SHA256="{YT_DLP_SHA256}"', "installer yt-dlp hash pin mismatch"),
            (f'DENO_SHA256="{DENO_SHA256}"', "installer Deno hash pin mismatch"),
            ('--js-runtimes "deno:$HERE/deno"', "yt-dlp wrapper does not explicitly use Deno"),
            ('actual="$(sha256sum "$file" | awk', "tool bootstrap does not calculate downloaded SHA-256"),
            ('if [[ "$actual" != "$expected" ]]', "tool bootstrap does not compare downloaded SHA-256"),
        ):
            if needle not in text:
                failures.append(message)

    workflow = root / ".github/workflows/transcribe.yml"
    if workflow.is_file():
        text = workflow.read_text(encoding="utf-8")
        for needle, message in (
            ("runs-on: [self-hosted, linux, x64, webactueel-transcribe]", "transcribe workflow is not bound to dedicated self-hosted runner"),
            ("branches: [runtime-requests]", "transcribe workflow must use runtime-requests branch"),
            ("python3 scripts/channel_runtime.py", "workflow does not run channel runtime"),
            ("--result pending", "queue workflow does not publish pending self-hosted status"),
            ("Verify dedicated runner boundary", "runner boundary verification was removed"),
            ("Attest result checksum receipt", "result attestation was removed"),
        ):
            if needle not in text:
                failures.append(message)
        if "python3 scripts/captions_runtime.py" in text:
            failures.append("workflow still exposes old single-video runtime")
        if "workflow_dispatch:" in text or "workflow_call:" in text:
            failures.append("transcribe workflow must remain queue-triggered only")

    return {"ok": not failures, "failures": failures, "required_count": len(REQUIRED), "forbidden_count": len(FORBIDDEN)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="local")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_checks()
    payload = {"mode": args.mode, **result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("repository-doctor: OK" if result["ok"] else "repository-doctor: FAILED")
        for failure in result["failures"]:
            print(f"- {failure}")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
