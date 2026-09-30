import importlib.util
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load("resolver", "scripts/resolve_request.py")
captions = load("captions", "scripts/captions_runtime.py")


class ChannelRequestTests(unittest.TestCase):
    def test_handle_normalizes_to_videos(self):
        out = resolver.validate_request({"enabled": True, "request_id": "channel-001", "url": "https://www.youtube.com/@BrianCoords", "language": "auto"})
        self.assertEqual(out["url"], "https://www.youtube.com/@BrianCoords/videos")
        self.assertEqual(out["year"], 2026)
        self.assertEqual(out["max_videos"], 1000)
        self.assertEqual(out["comments_per_video"], 7)
        self.assertFalse(out["include_replies"])

    def test_direct_video_is_rejected(self):
        with self.assertRaises(ValueError):
            resolver.validate_request({"enabled": True, "request_id": "channel-002", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

    def test_short_is_rejected(self):
        with self.assertRaises(ValueError):
            resolver.validate_request({"enabled": True, "request_id": "channel-003", "url": "https://www.youtube.com/shorts/dQw4w9WgXcQ"})

    def test_playlist_is_rejected(self):
        with self.assertRaises(ValueError):
            resolver.validate_request({"enabled": True, "request_id": "channel-004", "url": "https://www.youtube.com/playlist?list=abc"})


class RuntimePolicyTests(unittest.TestCase):
    def test_toolkit_contract_bounds_video_concurrency_to_seven(self):
        contract = json.loads((ROOT / 'toolkit-contract.json').read_text(encoding='utf-8'))
        self.assertEqual(contract['fixed_policy']['video_concurrency'], 7)
        self.assertEqual(contract['runtime_target'], 'github-hosted-only-or-local-direct-network')
        self.assertTrue(any('at most 7 concurrently active videos' in item for item in contract['boundaries']))
        self.assertTrue(any('no self-hosted runner' in item for item in contract['boundaries']))


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.old_comments_payload = captions.innertube.comments_payload
        self.old_run = captions.run

    def tearDown(self):
        captions.innertube.comments_payload = self.old_comments_payload
        captions.run = self.old_run

    def test_comments_prefer_bounded_innertube_top_without_replies(self):
        seen = {}
        def fake_payload(url, *, max_comments, comment_sort, include_replies):
            seen.update({
                "url": url,
                "max_comments": max_comments,
                "comment_sort": comment_sort,
                "include_replies": include_replies,
            })
            return {"comments": [
                {"id": str(i), "parent": "root", "text": f"c{i}", "like_count": i}
                for i in range(10)
            ]}
        captions.innertube.comments_payload = fake_payload
        captions.run = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("yt-dlp fallback should not run"))

        comments, status = captions.load_top_comments("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 7)

        self.assertEqual(status, "ok")
        self.assertEqual(len(comments), 7)
        self.assertEqual(seen["max_comments"], "7")
        self.assertEqual(seen["comment_sort"], "top")
        self.assertFalse(seen["include_replies"])

    def test_comment_fallback_keeps_top_limit_and_filters_replies(self):
        calls = []
        captions.innertube.comments_payload = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable"))

        def fake(command, timeout=240):
            calls.append(command)
            payload = {
                "comments": [
                    {"id": "1", "parent": "root", "text": "parent"},
                    {"id": "2", "parent": "1", "text": "reply"},
                ]
            }
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

        captions.run = fake
        comments, status = captions.load_top_comments("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 7)

        self.assertEqual(status, "ok")
        self.assertEqual([c["text"] for c in comments], ["parent"])
        joined = " ".join(calls[0])
        self.assertIn("comment_sort=top", joined)
        self.assertIn("max_comments=7,7,0,0,1", joined)
        self.assertIn("--write-comments", calls[0])


if __name__ == "__main__":
    unittest.main()
