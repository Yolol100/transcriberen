import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

# Runtime imports Trafilatura in CI after requirements installation. Provide a
# minimal local stub so the policy tests remain dependency-light as well.
if "trafilatura" not in sys.modules:
    stub = types.ModuleType("trafilatura")
    stub.__version__ = "test"
    stub.extract = lambda *args, **kwargs: ""
    sys.modules["trafilatura"] = stub

scripts_dir = pathlib.Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(scripts_dir))
MODULE_PATH = scripts_dir / "runtime.py"
spec = importlib.util.spec_from_file_location("transcribe_runtime", MODULE_PATH)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimePolicyTests(unittest.TestCase):
    def test_youtube_hosts_are_classified_as_captions_only(self):
        self.assertTrue(runtime.is_public_youtube("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(runtime.is_public_youtube("https://youtu.be/abc"))

    def test_youtube_extractor_is_classified_even_with_redirected_url(self):
        self.assertTrue(runtime.is_public_youtube("https://example.com/video", {"extractor": "Youtube", "webpage_url": "https://example.com/video"}))

    def test_non_youtube_media_is_not_classified_as_youtube(self):
        self.assertFalse(runtime.is_public_youtube("https://media.example.com/audio.mp3", {"extractor": "Generic"}))

    def test_generic_single_media_base_stays_no_playlist(self):
        self.assertIn("--no-playlist", runtime.yt_base())

    def test_generic_base_omits_removed_no_netrc_option(self):
        cmd = runtime.yt_base()
        self.assertNotIn("--no-netrc", cmd)
        self.assertIn("--no-config", cmd)
        self.assertIn("--no-cookies", cmd)

    def test_youtube_base_omits_removed_no_netrc_option(self):
        cmd = runtime.youtube_runtime.yt_base()
        self.assertNotIn("--no-netrc", cmd)
        self.assertIn("--no-config", cmd)
        self.assertIn("--no-cookies", cmd)
        self.assertIn("--skip-download", cmd)

    def test_bot_challenge_is_recognized_without_bypass(self):
        self.assertTrue(runtime.is_youtube_access_blocked_error("Sign in to confirm you’re not a bot"))
        self.assertFalse(runtime.is_youtube_access_blocked_error("video unavailable"))

    def test_blocked_collection_writes_valid_negative_evidence(self):
        req = {
            "youtube": {"scope": "search", "query": "test", "candidate_limit": 5, "include_comments": False},
            "analysis_content_allowed": True,
            "reuse_allowed": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            content, index = runtime.blocked_youtube_collection(req, RuntimeError("Sign in to confirm you’re not a bot"), tmp)
            self.assertEqual(index["collection_status"], "access_blocked")
            self.assertTrue(index["discovery"]["access_blocked"])
            self.assertEqual(index["discovery_errors"][0]["kind"], "access_blocked")
            self.assertTrue((pathlib.Path(tmp) / "youtube-index.json").is_file())
            self.assertEqual((pathlib.Path(tmp) / "content.md").read_text(), content)
            self.assertEqual(json.loads((pathlib.Path(tmp) / "youtube-index.json").read_text())["selected_count"], 0)

    def test_runtime_subprocess_timeout_is_fail_closed(self):
        expired = subprocess.TimeoutExpired(["tool"], 1, output=b"partial", stderr=b"stuck")
        with mock.patch.object(runtime.subprocess, "run", side_effect=expired):
            with self.assertRaisesRegex(RuntimeError, "timed out after 1s"):
                runtime.run(["tool"], timeout=1)

    def test_runtime_subprocess_timeout_returns_124_when_check_false(self):
        expired = subprocess.TimeoutExpired(["tool"], 1, output=b"partial", stderr=b"stuck")
        with mock.patch.object(runtime.subprocess, "run", side_effect=expired):
            completed = runtime.run(["tool"], timeout=1, check=False)
        self.assertEqual(completed.returncode, 124)
        self.assertIn("timed out after 1s", completed.stderr)

    def test_youtube_commands_use_bounded_process_adapter(self):
        sentinel = subprocess.CompletedProcess(["yt-dlp"], 0, "", "")
        with mock.patch.object(runtime, "run", return_value=sentinel) as bounded:
            result = runtime.youtube_runtime.run(["yt-dlp", "--write-comments"], check=False)
        self.assertIs(result, sentinel)
        bounded.assert_called_once_with(
            ["yt-dlp", "--write-comments"],
            check=False,
            timeout=runtime.YOUTUBE_COMMENT_TIMEOUT_SECONDS,
        )

    def test_xml_dtd_and_entity_declarations_are_rejected(self):
        payload = b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss><channel><link>&x;</link></channel></rss>'
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            runtime.parse_xml_links(payload, "https://example.com/feed.xml", "feed")

    def test_authorized_audio_duration_is_bounded_before_download(self):
        req = {
            "url": "https://media.example.com/audio.mp3",
            "language": "auto",
            "allow_audio_fallback": True,
            "audio_access_authorized": True,
        }
        meta = {
            "extractor": "Generic",
            "duration": runtime.MAX_AUTHORIZED_AUDIO_DURATION_SECONDS + 1,
            "webpage_url": req["url"],
        }
        completed = subprocess.CompletedProcess(["yt-dlp"], 0, "", "")
        with mock.patch.object(runtime, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "audio duration exceeds"):
                runtime.media_content(req, meta)


if __name__ == "__main__":
    unittest.main()