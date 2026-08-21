import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("resolve_request", ROOT / "scripts" / "resolve_request.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class RequestContractTests(unittest.TestCase):
    def base(self, url):
        return {"enabled": True, "request_id": "request-001", "url": url, "language": "auto"}

    def test_watch_url_is_normalized(self):
        result = m.validate_request(self.base("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=abc"))
        self.assertEqual(result["source_type"], "video")
        self.assertEqual(result["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_short_url_is_accepted(self):
        result = m.validate_request(self.base("https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share"))
        self.assertEqual(result["source_type"], "short")
        self.assertEqual(result["url"], "https://www.youtube.com/shorts/dQw4w9WgXcQ")

    def test_youtu_be_is_single_video(self):
        result = m.validate_request(self.base("https://youtu.be/dQw4w9WgXcQ?t=3"))
        self.assertEqual(result["source_type"], "video")
        self.assertEqual(result["video_id"], "dQw4w9WgXcQ")

    def test_search_channel_and_playlist_only_urls_are_rejected(self):
        bad = [
            "https://www.youtube.com/results?search_query=seo",
            "https://www.youtube.com/@ahrefs",
            "https://www.youtube.com/playlist?list=PL123",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.validate_request(self.base(url))

    def test_old_complex_fields_are_rejected(self):
        request = self.base("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        request["youtube"] = {"include_comments": True}
        with self.assertRaisesRegex(ValueError, "unsupported request fields"):
            m.validate_request(request)

    def test_only_expected_language_shape_is_allowed(self):
        request = self.base("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        request["language"] = "english please"
        with self.assertRaisesRegex(ValueError, "invalid language"):
            m.validate_request(request)


if __name__ == "__main__":
    unittest.main()
