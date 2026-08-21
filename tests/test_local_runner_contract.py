import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_local.sh"


class LocalRunnerContractTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reuses_canonical_contract_runtime_and_validator(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for needle in (
            "scripts/install_python_deps.sh",
            "scripts/install_tools.sh false",
            "scripts/resolve_request_hardened.py",
            "scripts/runtime_topic_filter.py",
            "scripts/normalize_youtube_result_v2.py",
            "scripts/validate_result.py",
            "SHA256SUMS.txt",
        ):
            self.assertIn(needle, text)

    def test_local_youtube_route_does_not_inherit_proxy_environment(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy",
            text,
        )
        self.assertNotIn("--cookies", text)
        self.assertNotIn("--proxy", text)

    def test_previous_results_are_preserved(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mv results "results.previous.$STAMP"', text)


if __name__ == "__main__":
    unittest.main()
