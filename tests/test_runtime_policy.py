import importlib.util
import pathlib
import subprocess
import types
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "runtime.py"
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

    def test_auto_youtube_does_not_fall_back_to_article_when_media_detection_is_blocked(self):
        req = {
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "mode": "auto",
            "language": "auto",
            "allow_audio_fallback": False,
            "audio_access_authorized": False,
        }
        expected = ("caption text", "subtitle", {}, [])
        with patch.object(runtime, "detect_media", return_value=None), \
             patch.object(runtime, "media_content", return_value=expected) as media_content, \
             patch.object(runtime, "fetch_public", side_effect=AssertionError("must not use article fallback")):
            self.assertEqual(runtime.extract(req), expected)
            media_content.assert_called_once_with(req, None)

    def test_youtube_command_failure_is_caption_access_error(self):
        req = {
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "language": "auto",
            "allow_audio_fallback": False,
            "audio_access_authorized": False,
        }
        meta = {"extractor": "Youtube", "webpage_url": req["url"]}
        failed = types.SimpleNamespace(returncode=1, stdout="", stderr="Sign in to confirm you're not a bot")
        with patch.object(runtime, "run", return_value=failed):
            with self.assertRaises(runtime.CaptionAccessError):
                runtime.media_content(req, meta)

    def test_youtube_success_without_caption_files_is_unavailable_not_access_error(self):
        req = {
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "language": "auto",
            "allow_audio_fallback": False,
            "audio_access_authorized": False,
        }
        meta = {"extractor": "Youtube", "webpage_url": req["url"]}
        ok = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(runtime, "run", return_value=ok):
            with self.assertRaises(runtime.CaptionUnavailableError):
                runtime.media_content(req, meta)

    def test_yt_dlp_is_forced_to_direct_connection_with_bounded_retries(self):
        command = runtime.yt_base()
        self.assertEqual(command[command.index("--proxy") + 1], "")
        self.assertEqual(command[command.index("--socket-timeout") + 1], "30")
        self.assertEqual(command[command.index("--retries") + 1], "3")
        self.assertEqual(command[command.index("--extractor-retries") + 1], "3")
        self.assertIn("--no-cookies", command)

    def test_request_hash_is_stable_across_key_order(self):
        first = {"b": 2, "a": {"y": True, "x": 1}}
        second = {"a": {"x": 1, "y": True}, "b": 2}
        self.assertEqual(runtime.canonical_request_sha256(first), runtime.canonical_request_sha256(second))

    def test_command_timeout_is_fail_closed(self):
        timeout = subprocess.TimeoutExpired(cmd=["x"], timeout=1, output="partial", stderr="late")
        with patch.object(runtime.subprocess, "run", side_effect=timeout):
            completed = runtime.run(["x"], check=False, timeout=1)
            self.assertEqual(completed.returncode, 124)
            self.assertIn("timed out", completed.stderr)
        with patch.object(runtime.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                runtime.run(["x"], timeout=1)

    def test_xml_dtd_and_entities_are_rejected(self):
        malicious = b'<!DOCTYPE foo [<!ENTITY xxe "x">]><urlset></urlset>'
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            runtime.parse_xml_links(malicious, "https://example.com/sitemap.xml", "sitemap")

    def test_authorized_audio_duration_is_bounded_before_download(self):
        req = {
            "url": "https://media.example.com/audio.mp3",
            "language": "auto",
            "allow_audio_fallback": True,
            "audio_access_authorized": True,
        }
        meta = {
            "extractor": "Generic",
            "webpage_url": req["url"],
            "duration": runtime.MAX_AUTHORIZED_AUDIO_DURATION_SECONDS + 1,
        }
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(runtime, "run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "duration exceeds"):
                runtime.media_content(req, meta)
        self.assertEqual(len(calls), 1, "duration gate must stop before audio download")


if __name__ == "__main__":
    unittest.main()
