import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "youtube_runtime.py"
spec = importlib.util.spec_from_file_location("youtube_runtime_resilience", MODULE_PATH)
youtube_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(youtube_runtime)


class YoutubeResilienceTests(unittest.TestCase):
    def test_top_40_comments_are_top_level_and_incomplete_data_fails(self):
        cmd = youtube_runtime._json_command(
            "https://www.youtube.com/watch?v=abcdefghijk",
            comments=True,
            comment_sort="top",
            max_comments="40",
            include_replies=False,
        )
        joined = " ".join(cmd)
        self.assertIn("--skip-download", cmd)
        self.assertIn("--no-cookies", cmd)
        self.assertIn("--write-comments", cmd)
        self.assertIn("comment_sort=top", joined)
        self.assertIn("max_comments=40,40,0,0,1", joined)
        self.assertIn("raise_incomplete_data=1", joined)

    def test_replies_require_explicit_opt_in(self):
        cmd = youtube_runtime._json_command(
            "https://www.youtube.com/watch?v=abcdefghijk",
            comments=True,
            max_comments="40",
            include_replies=True,
        )
        self.assertIn("max_comments=40,all,all,all,all", " ".join(cmd))

    def test_subtitle_client_fallback_stays_accountless(self):
        cmd = youtube_runtime.subtitle_command(
            "https://www.youtube.com/watch?v=abcdefghijk",
            {"language": "en", "kind": "manual"},
            "/tmp/source.%(ext)s",
            player_client="tv",
        )
        joined = " ".join(cmd)
        self.assertIn("player_client=tv", joined)
        self.assertIn("--skip-download", cmd)
        self.assertIn("--no-cookies", cmd)
        self.assertNotIn("--cookies-from-browser", joined)
        self.assertNotIn("po_token=", joined)

    def test_rate_limit_uses_long_cooldown(self):
        class Completed:
            returncode = 1
            stderr = "ERROR: HTTP Error 429: Too Many Requests"
        self.assertEqual(youtube_runtime._retry_delays_for(Completed()), youtube_runtime.RATE_LIMIT_RETRY_DELAYS)

    def test_hard_timeout_is_not_multiplied(self):
        class Completed:
            returncode = 124
            stderr = "command timed out"
        self.assertEqual(youtube_runtime._retry_delays_for(Completed()), ())

    def test_workflow_exposes_automatic_and_manual_transports(self):
        workflow = (ROOT / ".github" / "workflows" / "transcribe.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("workflow_call:", workflow)
        self.assertIn("branches: [runtime-requests]", workflow)
        self.assertIn("requests/queue/*.json", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("resolve_request_hardened.py", workflow)


if __name__ == "__main__":
    unittest.main()
