import importlib.util
import pathlib
import unittest

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

    def test_accountless_ytdlp_base_does_not_enable_or_negate_netrc(self):
        args = runtime.yt_base()
        self.assertNotIn("--netrc", args)
        self.assertNotIn("--no-netrc", args)
        self.assertIn("--no-cookies", args)
        self.assertIn("--no-config", args)


if __name__ == "__main__":
    unittest.main()
