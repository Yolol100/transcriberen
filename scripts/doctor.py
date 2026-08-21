#!/usr/bin/env python3
"""Offline repository preflight for the Transcriberen controlled runtime."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA_VERSION = "1.2"
EXPECTED_SOURCE_SET = "2.1.0-public-analysis"
EXPECTED_OWNER = "webactueel-workflow"
EXPECTED_PROJECT = "project-transcriberen"
EXPECTED_REPOSITORY = "Yolol100/transcriberen"

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "SECURITY.md",
    "THREAT-MODEL.md",
    "toolkit-contract.json",
    "requirements.txt",
    "requirements.lock",
    ".github/REPOSITORY-GOVERNANCE.md",
    ".github/workflows/codeql.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/doctor.yml",
    ".github/workflows/lock-audit.yml",
    ".github/workflows/toolkit-contract.yml",
    ".github/workflows/transcribe.yml",
    ".github/workflows/transcribe-self-hosted.yml",
    ".github/workflows/transcribe-readback-bridge.yml",
    "scripts/install_tools.sh",
    "scripts/publish_ci_status.py",
    "scripts/resolve_request.py",
    "scripts/resolve_request_hardened.py",
    "scripts/runtime.py",
    "scripts/youtube_runtime.py",
)

PIN_BINDINGS = (
    ("yt-dlp", "YT_DLP_VERSION", "YT_DLP_SHA256", False),
    ("deno-ejs-runtime", "DENO_VERSION", "DENO_SHA256", True),
    ("whisper.cpp", "WHISPER_VERSION", "WHISPER_SHA256", False),
)


def _result(name: str, ok: bool, detail: str, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "severity": severity}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _shell_assignment(text: str, name: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(name)}="([^"]+)"\s*$', text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _contract_tool(contract: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
    tools = contract.get("tools")
    if not isinstance(tools, list):
        return None
    for tool in tools:
        if isinstance(tool, dict) and tool.get("id") == tool_id:
            return tool
    return None


def _normalize_version(value: str | None, strip_v: bool) -> str | None:
    if value is None:
        return None
    return value[1:] if strip_v and value.startswith("v") else value


def check_repository(root: Path, mode: str = "local") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    missing = [relative for relative in REQUIRED_FILES if not (root / relative).is_file()]
    checks.append(
        _result(
            "required-files",
            not missing,
            "all required repository files present" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    contract_path = root / "toolkit-contract.json"
    contract: dict[str, Any] = {}
    if contract_path.is_file():
        try:
            loaded = json.loads(_read(contract_path))
            if isinstance(loaded, dict):
                contract = loaded
                checks.append(_result("contract-json", True, "toolkit-contract.json parses"))
            else:
                checks.append(_result("contract-json", False, "toolkit-contract.json must contain an object"))
        except (OSError, json.JSONDecodeError) as exc:
            checks.append(_result("contract-json", False, f"invalid toolkit contract: {exc}"))
    else:
        checks.append(_result("contract-json", False, "toolkit-contract.json missing"))

    expected_fields = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "source_set_version": EXPECTED_SOURCE_SET,
        "owner_skill": EXPECTED_OWNER,
        "project_id": EXPECTED_PROJECT,
        "repository": EXPECTED_REPOSITORY,
    }
    for key, expected in expected_fields.items():
        actual = contract.get(key)
        checks.append(_result(f"contract-{key}", actual == expected, f"expected {expected!r}; found {actual!r}"))

    for key in ("requires_account", "requires_api_key", "requires_mcp"):
        actual = contract.get(key)
        checks.append(_result(f"contract-{key}", actual is False, f"expected false; found {actual!r}"))

    install_tools = root / "scripts/install_tools.sh"
    install_text = _read(install_tools) if install_tools.is_file() else ""
    for tool_id, version_name, sha_name, strip_v in PIN_BINDINGS:
        tool = _contract_tool(contract, tool_id)
        shell_version = _normalize_version(_shell_assignment(install_text, version_name), strip_v)
        contract_version = _normalize_version(str(tool.get("version")) if tool else None, strip_v)
        shell_sha = _shell_assignment(install_text, sha_name)
        contract_sha = str(tool.get("sha256")) if tool and tool.get("sha256") else None
        checks.append(
            _result(
                f"pin-{tool_id}-version",
                bool(shell_version) and shell_version == contract_version,
                f"installer={shell_version!r}; contract={contract_version!r}",
            )
        )
        checks.append(
            _result(
                f"pin-{tool_id}-sha256",
                bool(shell_sha) and shell_sha == contract_sha,
                f"installer={shell_sha!r}; contract={contract_sha!r}",
            )
        )

    model_tool = _contract_tool(contract, "whisper-base-model")
    model_revision = _shell_assignment(install_text, "WHISPER_MODEL_REVISION")
    model_sha = _shell_assignment(install_text, "WHISPER_MODEL_SHA256")
    expected_model_version = f"hf-{model_revision}" if model_revision else None
    checks.append(
        _result(
            "pin-whisper-model-version",
            bool(model_tool) and model_tool.get("version") == expected_model_version,
            f"installer={expected_model_version!r}; contract={model_tool.get('version') if model_tool else None!r}",
        )
    )
    checks.append(
        _result(
            "pin-whisper-model-sha256",
            bool(model_tool) and model_tool.get("sha256") == model_sha and bool(model_sha),
            f"installer={model_sha!r}; contract={model_tool.get('sha256') if model_tool else None!r}",
        )
    )

    requirements_txt = root / "requirements.txt"
    req_text = _read(requirements_txt).strip() if requirements_txt.is_file() else ""
    checks.append(_result("requirements-entrypoint", req_text == "-r requirements.lock", f"found {req_text!r}"))

    lock_path = root / "requirements.lock"
    lock_lines = []
    if lock_path.is_file():
        lock_lines = [
            line.strip()
            for line in _read(lock_path).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    hashed_lock = bool(lock_lines) and all("--hash=sha256:" in line for line in lock_lines)
    checks.append(_result("requirements-hashed-lock", hashed_lock, f"validated {len(lock_lines)} locked entries"))

    workflow_expectations = {
        ".github/workflows/transcribe.yml": (
            "workflow_dispatch:",
            "workflow_call:",
            "branches: [runtime-requests]",
            "requests/queue/*.json",
            "ref: main",
        ),
        ".github/workflows/transcribe-self-hosted.yml": (
            "runtime-requests-selfhosted",
            "webactueel-transcribe",
            "ref: main",
        ),
        ".github/workflows/doctor.yml": (
            "python scripts/doctor.py --mode ci --json",
            "python -m unittest discover -s tests -p 'test_doctor.py' -v",
            "post-merge/Repository Doctor",
            "statuses: write",
        ),
        ".github/workflows/lock-audit.yml": (
            "requirements.generated.lock",
            "--require-hashes",
            "diff -u requirements.lock requirements.generated.lock",
        ),
    }
    for relative, needles in workflow_expectations.items():
        path = root / relative
        text = _read(path) if path.is_file() else ""
        absent = [needle for needle in needles if needle not in text]
        checks.append(
            _result(
                f"workflow-{Path(relative).stem}",
                not absent,
                "required workflow invariants present" if not absent else f"missing: {', '.join(absent)}",
            )
        )

    self_hosted = root / ".github/workflows/transcribe-self-hosted.yml"
    self_hosted_text = _read(self_hosted) if self_hosted.is_file() else ""
    forbidden_self_hosted = [trigger for trigger in ("pull_request:", "pull_request_target:") if trigger in self_hosted_text]
    checks.append(
        _result(
            "self-hosted-untrusted-pr-trigger",
            not forbidden_self_hosted,
            "no untrusted PR trigger" if not forbidden_self_hosted else f"forbidden trigger(s): {', '.join(forbidden_self_hosted)}",
        )
    )

    if mode == "local":
        for executable in ("bash", "curl", "git", "python3", "sha256sum"):
            found = shutil.which(executable)
            checks.append(
                _result(
                    f"local-{executable}",
                    found is not None,
                    found or f"{executable} not found in PATH",
                )
            )
        ffmpeg = shutil.which("ffmpeg")
        checks.append(
            _result(
                "local-ffmpeg",
                ffmpeg is not None,
                ffmpeg or "ffmpeg not installed; only required for explicitly authorized non-YouTube audio fallback",
                severity="warning",
            )
        )

    errors = [check for check in checks if not check["ok"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["ok"] and check["severity"] == "warning"]
    return {
        "schema": "webactueel-transcriberen-doctor/1.0",
        "mode": mode,
        "repository": EXPECTED_REPOSITORY,
        "source_set_version": contract.get("source_set_version"),
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Transcriberen repository before runtime use.")
    parser.add_argument("--mode", choices=("ci", "local"), default="local")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    report = check_repository(root, mode=args.mode)
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for check in report["checks"]:
            if check["ok"]:
                marker = "PASS"
            elif check["severity"] == "warning":
                marker = "WARN"
            else:
                marker = "FAIL"
            print(f"[{marker}] {check['name']}: {check['detail']}")
        print(f"doctor: {'OK' if report['ok'] else 'FAILED'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
