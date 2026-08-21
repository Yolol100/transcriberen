import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_local.sh"


class LocalRunnerContractTests(unittest.TestCase):
    def test_local_runner_uses_same_minimal_pipeline(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("scripts/resolve_request.py", text)
        self.assertIn("scripts/captions_runtime.py", text)
        self.assertIn("scripts/validate_result.py", text)
        self.assertIn("scripts/install_tools.sh", text)

    def test_local_runner_has_no_python_dependency_or_audio_stack(self):
        text = SCRIPT.read_text(encoding="utf-8").casefold()
        for forbidden in ("install_python_deps", "venv", "ffmpeg", "whisper", "comments"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
