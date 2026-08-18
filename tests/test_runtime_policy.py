import importlib.util
import pathlib
import sys
import types
import unittest

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


if __name__ == "__main__":
    unittest.main()
