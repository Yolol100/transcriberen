import copy
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


youtube_runtime = load_module("youtube_runtime_remaining", ROOT / "scripts" / "youtube_runtime.py")
resolve_request = load_module("resolve_request_remaining", ROOT / "scripts" / "resolve_request.py")

PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]

BASE = {
    "enabled": True,
    "request_id": "remaining-test-001",
    "owner": "webactueel-workflow",
    "project_id": "project-transcriberen",
    "url": "https://example.com/source",
    "mode": "article",
    "language": "auto",
    "allow_audio_fallback": False,
    "audio_access_authorized": False,
    "analysis_content_allowed": False,
    "reuse_allowed": False,
    "rights_basis": "analysis-paraphrase-only",
    "source_context": {"project_id": "project-transcriberen", "source_set_version": "1.9.0-test"},
}


class RemainingScenarioTests(unittest.TestCase):
    def test_channel_all_includes_videos_shorts_and_streams(self):
        req = {
            "url": "https://www.youtube.com/@example",
            "youtube": {"scope": "channel_all", "max_items": 6, "scan_limit": 6, "sort_by": "relevance"},
        }

        def fake_json(cmd):
            source = cmd[-1]
            prefix = "V" if source.endswith("/videos") else "S" if source.endswith("/shorts") else "L"
            return {
                "playlist_count": 2,
                "entries": [{"id": f"{prefix}{i}", "title": f"{prefix}{i}"} for i in range(1, 3)],
            }

        with mock.patch.object(youtube_runtime, "load_json", side_effect=fake_json):
            entries, info = youtube_runtime.discover_candidates_detailed(req)

        self.assertEqual([x["id"] for x in entries], ["V1", "S1", "L1", "V2", "S2", "L2"])
        self.assertEqual([x["source"].rsplit("/", 1)[-1] for x in info["sources"]], ["videos", "shorts", "streams"])

    def test_random_selection_is_reproducible_for_request_seed(self):
        items = [
            {"meta": {"id": "a"}},
            {"meta": {"id": "b"}},
            {"meta": {"id": "c"}},
            {"meta": {"id": "d"}},
        ]
        seed = "request-123"
        ranked = youtube_runtime.rank_metadata(items, "random", seed)
        expected = sorted(
            items,
            key=lambda item: hashlib.sha256(f"{seed}\0{item['meta']['id']}".encode("utf-8")).digest(),
        )
        self.assertEqual(ranked, expected)
        self.assertEqual(ranked, youtube_runtime.rank_metadata(items, "random", seed))

    def test_random_bulk_selection_scans_budget_before_sampling(self):
        req = {
            "url": "https://www.youtube.com/@example",
            "youtube": {"scope": "channel_all", "max_items": 1, "scan_limit": 50, "sort_by": "random"},
        }
        self.assertEqual(youtube_runtime._discovery_playlist_end(req), 50)

    def test_collect_records_random_seed_and_uses_seeded_order(self):
        req = {
            "request_id": "random-run-001",
            "language": "auto",
            "analysis_content_allowed": False,
            "reuse_allowed": False,
            "youtube": {"scope": "search", "query": "seo", "max_items": 1, "sort_by": "random", "include_comments": False},
        }
        candidates = [
            {"url": "https://www.youtube.com/watch?v=a", "id": "a"},
            {"url": "https://www.youtube.com/watch?v=b", "id": "b"},
        ]
        metas = {
            candidates[0]["url"]: {"id": "a", "title": "A", "webpage_url": candidates[0]["url"]},
            candidates[1]["url"]: {"id": "b", "title": "B", "webpage_url": candidates[1]["url"]},
        }
        expected_first = youtube_runtime.rank_metadata(
            [{"order": i, "url": c["url"], "meta": metas[c["url"]]} for i, c in enumerate(candidates)],
            "random",
            req["request_id"],
        )[0]["meta"]["id"]

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(youtube_runtime, "discover_candidates_detailed", return_value=(candidates, {"scan_limit": None, "candidate_limit": 2, "possibly_truncated": False, "sources": []})), \
             mock.patch.object(youtube_runtime, "metadata_for", side_effect=lambda url: metas[url]), \
             mock.patch.object(youtube_runtime, "download_caption", return_value=("caption", {"language": "en", "kind": "manual"})):
            _, index = youtube_runtime.collect(req, tmp)

        self.assertEqual(index["random_seed"], req["request_id"])
        self.assertEqual(index["selected_count"], 1)
        self.assertEqual(index["items"][0]["id"], expected_first)

    def test_random_sort_is_accepted_by_request_contract(self):
        req = {
            "url": "https://www.youtube.com/@example",
            "youtube": {"scope": "channel_all", "sort_by": "random", "max_items": 1},
        }
        with mock.patch.object(resolve_request, "validate_youtube_scope_url", return_value=req["url"]):
            validated = resolve_request.validate_youtube(req)
        self.assertEqual(validated["youtube"]["sort_by"], "random")

    def test_placeholder_source_set_is_rejected(self):
        request = copy.deepcopy(BASE)
        request["source_context"]["source_set_version"] = "set-at-execution"
        with mock.patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            with self.assertRaisesRegex(ValueError, "concrete current source set"):
                resolve_request.validate_request(request)

    def test_workflow_pins_resolve_runner_and_exposes_random(self):
        workflow = (ROOT / ".github" / "workflows" / "transcribe.yml").read_text(encoding="utf-8")
        self.assertIn("resolve:\n    runs-on: ubuntu-24.04", workflow)
        self.assertIn("options: [relevance, views, likes, comments, newest, random]", workflow)
        source_input = workflow.split("source_set_version:", 1)[1].split("permissions:", 1)[0]
        self.assertIn("required: true", source_input)
        self.assertNotIn("default:", source_input)


if __name__ == "__main__":
    unittest.main()