import hashlib
import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

youtube_runtime = load("youtube_runtime_remaining", ROOT / "scripts" / "youtube_runtime.py")
resolve_request = load("resolve_request_remaining", ROOT / "scripts" / "resolve_request.py")


class RemainingScenarioTests(unittest.TestCase):
    def test_channel_all_includes_videos_shorts_and_streams(self):
        req = {"url": "https://www.youtube.com/@example", "youtube": {"scope": "channel_all", "max_items": 6, "scan_limit": 6, "sort_by": "relevance"}}
        def fake_json(cmd):
            source = cmd[-1]
            prefix = "V" if source.endswith("/videos") else "S" if source.endswith("/shorts") else "L"
            return {"playlist_count": 2, "entries": [{"id": f"{prefix}{i}", "title": f"{prefix}{i}"} for i in range(1, 3)]}
        with mock.patch.object(youtube_runtime, "load_json", side_effect=fake_json):
            entries, info = youtube_runtime.discover_candidates_detailed(req)
        self.assertEqual([x["id"] for x in entries], ["V1", "S1", "L1", "V2", "S2", "L2"])
        self.assertEqual([x["source"].rsplit("/", 1)[-1] for x in info["sources"]], ["videos", "shorts", "streams"])

    def test_random_selection_is_reproducible_for_request_seed(self):
        items = [{"meta": {"id": x}} for x in "abcd"]
        seed = "request-123"
        ranked = youtube_runtime.rank_metadata(items, "random", seed)
        expected = sorted(items, key=lambda item: hashlib.sha256(f"{seed}\0{item['meta']['id']}".encode()).digest())
        self.assertEqual(ranked, expected)

    def test_placeholder_source_set_is_rejected(self):
        request = {"enabled": True, "request_id": "remaining-test-001", "owner": "webactueel-workflow", "project_id": "project-transcriberen", "url": "https://example.com/source", "mode": "article", "language": "auto", "allow_audio_fallback": False, "audio_access_authorized": False, "analysis_content_allowed": False, "reuse_allowed": False, "rights_basis": "analysis-paraphrase-only", "source_context": {"project_id":"project-transcriberen","source_set_version":"set-at-execution"}}
        with mock.patch.object(resolve_request.socket, "getaddrinfo", return_value=[(2,1,6,"",("93.184.216.34",443))]):
            with self.assertRaisesRegex(ValueError, "concrete current source set"):
                resolve_request.validate_request(request)

    def test_all_comments_unbounded_still_has_hard_item_cap(self):
        req = {"url": "https://www.youtube.com/@example", "youtube": {"scope":"channel_all","max_items":5,"scan_limit":0,"allow_unbounded":True,"include_comments":True,"max_comments":"all"}}
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            validated = resolve_request.validate_youtube(req)
        self.assertEqual(validated["youtube"]["max_items"], 5)
        req["youtube"]["max_items"] = 6
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            with self.assertRaisesRegex(ValueError, "between 1 and 5"):
                resolve_request.validate_youtube(req)


if __name__ == "__main__":
    unittest.main()
