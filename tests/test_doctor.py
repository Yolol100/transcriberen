import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class DoctorTests(unittest.TestCase):
    def test_current_minimal_tree_passes(self):
        result = m.run_checks(ROOT)
        self.assertTrue(result["ok"], result["failures"])

    def build_minimal_tree(self, root):
        for relative in m.REQUIRED:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "toolkit-contract.json":
                path.write_text(
                    '{"schema_version":"2.1","capability_id":"public-youtube-caption-acquisition",'
                    '"runtime_target":"self-hosted-or-local-direct-network",'
                    '"tools":[{"id":"yt-dlp"},{"id":"deno-ejs-runtime"}]}',
                    encoding="utf-8",
                )
            elif relative == ".github/workflows/transcribe.yml":
                path.write_text("branches: [runtime-requests]\nruns-on: [self-hosted, linux, x64, webactueel-transcribe]\n", encoding="utf-8")
            else:
                path.write_text("", encoding="utf-8")

    def test_obsolete_runtime_file_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.build_minimal_tree(root)
            obsolete = root / "scripts/runtime_topic_filter.py"
            obsolete.write_text("old", encoding="utf-8")
            result = m.run_checks(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("obsolete file" in item for item in result["failures"]))

    def test_project_truth_key_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.build_minimal_tree(root)
            contract = root / "toolkit-contract.json"
            contract.write_text(
                '{"schema_version":"2.1","capability_id":"public-youtube-caption-acquisition",'
                '"runtime_target":"self-hosted-or-local-direct-network","project_id":"example-project",'
                '"tools":[{"id":"yt-dlp"},{"id":"deno-ejs-runtime"}]}',
                encoding="utf-8",
            )
            result = m.run_checks(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("project truth keys" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
