#!/usr/bin/env python3
"""Publish a machine-readable CI result on the exact GitHub commit SHA."""
import argparse
import json
import os
import urllib.error
import urllib.request

API_VERSION = "2026-03-10"


def normalize_result(result):
    value = str(result or "").strip().lower()
    if value == "success":
        return "success"
    if value == "failure":
        return "failure"
    return "error"


def build_payload(context, result, repository, run_id):
    state = normalize_result(result)
    return {
        "state": state,
        "context": context,
        "description": f"{context}: {state}"[:140],
        "target_url": f"https://github.com/{repository}/actions/runs/{run_id}",
    }


def publish_status(context, result):
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    sha = os.environ.get("GITHUB_SHA", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is required")
    if len(sha) != 40:
        raise RuntimeError("GITHUB_SHA must be a full 40-character commit SHA")
    if not run_id.isdigit():
        raise RuntimeError("GITHUB_RUN_ID is required")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")

    payload = build_payload(context, result, repository, run_id)
    url = f"https://api.github.com/repos/{repository}/statuses/{sha}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "webactueel-transcriberen-ci",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"commit-status API failed with HTTP {exc.code}: {detail}") from exc
    print(json.dumps({
        "sha": sha,
        "context": body.get("context") or payload["context"],
        "state": body.get("state") or payload["state"],
        "target_url": body.get("target_url") or payload["target_url"],
    }))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    context = args.context.strip()
    if not context or len(context) > 100:
        raise SystemExit("--context must be 1..100 characters")
    publish_status(context, args.result)


if __name__ == "__main__":
    main()
