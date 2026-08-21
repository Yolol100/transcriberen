import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = ROOT / "scripts" / "doctor.py"

spec = importlib.util.spec_from_file_location("transcriberen_doctor", DOCTOR_PATH)
doctor = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_ci_repository_preflight_passes(self):
        report = doctor.check_repository(ROOT, mode="ci")
        failures = [check for check in report["checks"] if not check["ok"] and check["severity"] == "error"]
        self.assertTrue(report["ok"], failures)
        self.assertEqual([], failures)
        self.assertEqual("2.1.0-public-analysis", report["source_set_version"])

    def test_cli_json_report_is_machine_readable(self):
        completed = subprocess.run(
            [sys.executable, str(DOCTOR_PATH), "--mode", "ci", "--json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual("webactueel-transcriberen-doctor/1.0", payload["schema"])

    def test_local_ffmpeg_warning_only_when_missing(self):
        with mock.patch.object(doctor.shutil, "which", return_value="/usr/bin/tool"):
            report = doctor.check_repository(ROOT, mode="local")
        ffmpeg = next(check for check in report["checks"] if check["name"] == "local-ffmpeg")
        self.assertTrue(ffmpeg["ok"])
        self.assertEqual(0, report["warning_count"])

        def missing_ffmpeg(name):
            return None if name == "ffmpeg" else f"/usr/bin/{name}"

        with mock.patch.object(doctor.shutil, "which", side_effect=missing_ffmpeg):
            report = doctor.check_repository(ROOT, mode="local")
        ffmpeg = next(check for check in report["checks"] if check["name"] == "local-ffmpeg")
        self.assertFalse(ffmpeg["ok"])
        self.assertEqual("warning", ffmpeg["severity"])
        self.assertEqual(1, report["warning_count"])
        self.assertTrue(report["ok"])

    def test_required_files_cover_doctor_followup_and_lock_audit(self):
        self.assertIn("scripts/publish_ci_status.py", doctor.REQUIRED_FILES)
        self.assertIn(".github/workflows/lock-audit.yml", doctor.REQUIRED_FILES)

    def test_shell_assignment_is_exact(self):
        text = 'A="one"\nYT_DLP_VERSION="2026.08.20.234504"\n'
        self.assertEqual("2026.08.20.234504", doctor._shell_assignment(text, "YT_DLP_VERSION"))
        self.assertIsNone(doctor._shell_assignment(text, "MISSING"))


if __name__ == "__main__":
    unittest.main()
