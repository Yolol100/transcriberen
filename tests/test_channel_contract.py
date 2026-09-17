import importlib.util
import pathlib
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


class CommentTests(unittest.TestCase):
    def test_comment_command_is_top_and_seven_without_replies(self):
        calls = []
        old = captions.run
        try:
            def fake(command, timeout=240):
                calls.append(command)
                import subprocess, json
                payload = {"comments": [{"id": str(i), "parent": "root", "text": f"c{i}", "like_count": i} for i in range(10)]}
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")
            captions.run = fake
            comments, status = captions.load_top_comments("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 7)
        finally:
            captions.run = old
        self.assertEqual(status, "ok")
        self.assertEqual(len(comments), 7)
        joined = " ".join(calls[0])
        self.assertIn("comment_sort=top", joined)
        self.assertIn("max_comments=7,7,0,0,1", joined)
        self.assertIn("--write-comments", calls[0])

    def test_replies_are_filtered(self):
        import subprocess, json
        old = captions.run
        try:
            captions.run = lambda command, timeout=240: subprocess.CompletedProcess(command, 0, stdout=json.dumps({"comments": [{"id":"1","parent":"root","text":"parent"},{"id":"2","parent":"1","text":"reply"}]}), stderr="")
            comments, _ = captions.load_top_comments("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 7)
        finally:
            captions.run = old
        self.assertEqual([c["text"] for c in comments], ["parent"])


if __name__ == "__main__":
    unittest.main()
