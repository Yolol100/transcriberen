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
    "scripts/cache_runtime.py",
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
PROJECT_TRUTH_KEYS = {"owner_skill", "owner_mode", "project_id", "source_set_version"}
PROJECT_TRUTH_MARKERS = {"project-transcriberen", "2.2.0-captions-only"}
YT_DLP_VERSION = "2026.08.20.234504"
YT_DLP_SHA256 = "8962aa45f945ae5aa11ab49acab365e8baef569ec995149f99ae0ae3a19cae93"
DENO_VERSION = "2.9.5"
DENO_SHA256 = "8b010a3b1a4a0188a67cdb8a7a27348b2a501af78aec7fc74f2ace167368d530"


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
        if contract.get("schema_version") != "2.1":
            failures.append("toolkit schema_version must be 2.1")
        if contract.get("capability_id") != "public-youtube-caption-acquisition":
            failures.append("toolkit capability_id mismatch")
        if contract.get("runtime_target") != "self-hosted-or-local-direct-network":
            failures.append("runtime target must be self-hosted/local direct network")
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

    for relative in ("scripts/resolve_request.py", "scripts/captions_runtime.py", "scripts/cache_runtime.py", ".github/workflows/transcribe.yml"):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for term in FORBIDDEN_RUNTIME_TERMS:
            if term in text:
                failures.append(f"obsolete runtime term {term!r} remains in {relative}")

    runtime = root / "scripts/captions_runtime.py"
    if runtime.is_file() and '"--no-warnings"' in runtime.read_text(encoding="utf-8"):
        failures.append("yt-dlp warnings must remain visible for access-block classification")

    cache = root / "scripts/cache_runtime.py"
    if cache.is_file():
        text = cache.read_text(encoding="utf-8")
        for needle, message in (
            ("history.sqlite3", "persistent cache database is not configured"),
            ("processed-index.json", "processed index export is missing"),
            ("PRIMARY KEY (video_id, requested_language)", "cache does not deduplicate by video/language"),
            ("cache_hit", "cache hit evidence is missing"),
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
        if "runs-on: [self-hosted, linux, x64, webactueel-transcribe]" not in text:
            failures.append("transcribe workflow is not bound to dedicated self-hosted runner")
        if "branches: [runtime-requests]" not in text:
            failures.append("transcribe workflow must use runtime-requests branch")
        if "--result pending" not in text:
            failures.append("queue workflow does not publish pending self-hosted status")
        if "python3 scripts/cache_runtime.py precheck" not in text:
            failures.append("workflow does not precheck persistent cache")
        if "python3 scripts/cache_runtime.py finalize" not in text:
            failures.append("workflow does not persist/export cache history")

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
