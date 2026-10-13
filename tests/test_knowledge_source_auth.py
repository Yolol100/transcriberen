"""Do not use a failed, spoofed, or foreign-branch GitHub Actions artifact as source."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
RUN = {
    "name": "Transcribe Public Source",
    "repository": {"full_name": "Yolol100/transcriberen"},
    "event": "push",
    "head_branch": "runtime-requests",
    "status": "completed",
    "conclusion": "success",
    "path": ".github/workflows/transcribe.yml",
}

MOCK_GH = """#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
meta=json.loads(os.environ["MOCK_GITHUB_RUN"])
if args[0]=="api":
    key=args[args.index("--jq")+1]
    item=meta
    for part in key.strip("'").lstrip(".").split("."):
        item=item.get(part) if isinstance(item,dict) else None
        if item is None:
            break
    print("null" if item is None else item)
elif args[:2]==["run","download"]:
    root=pathlib.Path(args[args.index("--dir")+1])
    (root/"artifact").mkdir(parents=True,exist_ok=True)
    (root/"artifact"/"channel-corpus.zip").write_bytes(b"fixture bytes")
else:
    raise SystemExit("mock gh refuses unexpected command: "+str(args))
"""


def run_source(meta):
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        executable = home / "gh"
        executable.write_text(MOCK_GH, encoding="utf-8")
        executable.chmod(0o755)
        dest = home / "source"
        env = os.environ.copy()
        env.update({
            "PATH": str(home) + os.pathsep + env.get("PATH", ""),
            "GH_TOKEN": "nonsecret-mock-token",
            "GITHUB_REPOSITORY": "Yolol100/transcriberen",
            "MOCK_GITHUB_RUN": json.dumps(meta),
        })
        proc = subprocess.run(
            ["bash", str(REPO / "scripts" / "knowledge_source.sh"),
             "run", "1234567", str(dest)],
            env=env, capture_output=True, text=True, timeout=15,
        )
        files = (dest / "INPUT-FILES.txt").read_text() if (dest / "INPUT-FILES.txt").exists() else ""
        return proc.returncode, proc.stdout + proc.stderr, files


class RunArtifactProvenanceTests(unittest.TestCase):
    def test_only_successful_trusted_push_run_is_accepted(self):
        code, output, files = run_source(dict(RUN))
        self.assertEqual(code, 0, output)
        self.assertIn("channel-corpus.zip", files)

    def test_failed_cancelled_or_nonterminal_run_is_rejected(self):
        for key, value in [
            ("conclusion", "failure"), ("conclusion", "cancelled"),
            ("conclusion", "null"), ("status", "in_progress"),
        ]:
            with self.subTest(key=key, value=value):
                case = dict(RUN)
                case[key] = value
                code, output, files = run_source(case)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(files, "")

    def test_foreign_event_or_branch_is_rejected_despite_matching_name(self):
        for key, value in [("event", "pull_request"),
                           ("event", "workflow_dispatch"),
                           ("head_branch", "feature-untrusted")]:
            with self.subTest(key=key, value=value):
                case = dict(RUN)
                case[key] = value
                code, output, files = run_source(case)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(files, "")

    def test_another_workflow_with_a_matching_display_name_is_rejected(self):
        for path in [
            ".github/workflows/other.yml@runtime-requests",
            ".github/workflows/transcribe.yml@refs/heads/feature",
            "null",
        ]:
            with self.subTest(path=path):
                case = dict(RUN)
                case["path"] = path
                code, output, files = run_source(case)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(files, "")


if __name__ == "__main__":
    unittest.main()
