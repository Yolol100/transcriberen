import importlib.util
import pathlib
import sys
import types
import unittest

runtime = types.SimpleNamespace(RESULTS=pathlib.Path("results"))
sys.modules.setdefault("runtime", runtime)
MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "entrypoint.py"
spec = importlib.util.spec_from_file_location("entrypoint", MODULE_PATH)
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


class YoutubeCollectionTests(unittest.TestCase):
    def test_channel_handle_is_collection(self):
        self.assertTrue(entrypoint.is_youtube_collection_url("https://www.youtube.com/@OpenAI"))

    def test_playlist_is_collection(self):
        self.assertTrue(entrypoint.is_youtube_collection_url("https://www.youtube.com/playlist?list=PL123"))

    def test_single_video_is_not_collection(self):
        self.assertFalse(entrypoint.is_youtube_collection_url("https://www.youtube.com/watch?v=abcdefghijk"))

    def test_channel_normalizes_to_videos_tab(self):
        self.assertEqual(entrypoint.normalize_collection_url("https://www.youtube.com/@OpenAI"), "https://www.youtube.com/@OpenAI/videos")

    def test_playlist_url_is_preserved(self):
        url = "https://www.youtube.com/playlist?list=PL123"
        self.assertEqual(entrypoint.normalize_collection_url(url), url)


if __name__ == "__main__":
    unittest.main()
