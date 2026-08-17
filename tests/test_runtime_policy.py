import importlib.util
import pathlib
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


if __name__ == "__main__":
    unittest.main()
