import copy
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "resolve_request.py"
spec = importlib.util.spec_from_file_location("resolve_request", MODULE_PATH)
resolve_request = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolve_request)

PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE_DNS = [(2, 1, 6, "", ("127.0.0.1", 443))]
SOURCE_SET = "2.1.0-public-analysis"

BASE = {
    "enabled": True,
    "request_id": "transcribe-test-001",
    "owner": "webactueel-workflow",
    "project_id": "project-transcriberen",
    "url": "https://example.com/source",
    "mode": "article",
    "language": "auto",
    "allow_audio_fallback": False,
    "audio_access_authorized": False,
    "analysis_content_allowed": False,
    "reuse_allowed": False,
    "public_request_acknowledged": False,
    "rights_basis": "analysis-paraphrase-only",
    "source_context": {"project_id": "project-transcriberen", "source_set_version": SOURCE_SET},
}


def youtube_request(scope="video", url="https://www.youtube.com/watch?v=abcdefghijk"):
    request = copy.deepcopy(BASE)
    request.update({
        "mode": "youtube",
        "url": url,
        "youtube": {"scope": scope},
    })
    return request


class RequestContractTests(unittest.TestCase):
    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_valid_analysis_request(self, _dns):
        request = resolve_request.validate_request(copy.deepcopy(BASE))
        self.assertFalse(request["reuse_allowed"])
        self.assertFalse(request["audio_access_authorized"])
        self.assertEqual(request["language"], "auto")

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PRIVATE_DNS)
    def test_private_target_is_rejected(self, _dns):
        with self.assertRaisesRegex(ValueError, "non-public target"):
            resolve_request.validate_request(copy.deepcopy(BASE))

    def test_url_credentials_are_rejected_before_dns(self):
        request = copy.deepcopy(BASE)
        request["url"] = "https://user:secret@example.com/source"
        with self.assertRaisesRegex(ValueError, "credentials"):
            resolve_request.validate_request(request)

    def test_secret_query_parameter_is_rejected_before_dns(self):
        request = copy.deepcopy(BASE)
        request["url"] = "https://example.com/source?access_token=abc"
        with self.assertRaisesRegex(ValueError, "secret-like query"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_reuse_requires_concrete_rights_basis(self, _dns):
        request = copy.deepcopy(BASE)
        request["reuse_allowed"] = True
        with self.assertRaisesRegex(ValueError, "concrete verified rights_basis"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_authorized_audio_fallback_is_accepted(self, _dns):
        request = copy.deepcopy(BASE)
        request["mode"] = "media"
        request["allow_audio_fallback"] = True
        request["audio_access_authorized"] = True
        request["rights_basis"] = "client supplied media and authorized transcription"
        validated = resolve_request.validate_request(request)
        self.assertTrue(validated["allow_audio_fallback"])

    def test_youtube_search_needs_no_url(self):
        request = youtube_request()
        request.update({"url": "", "youtube": {"scope": "search", "query": "wordpress performance"}})
        validated = resolve_request.validate_request(request)
        self.assertIsNone(validated["url"])
        self.assertFalse(validated["analysis_content_allowed"])
        self.assertEqual(validated["youtube_access_basis"], "public-anonymous")

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_youtube_disallows_audio_fallback(self, _dns):
        request = youtube_request()
        request.update({"allow_audio_fallback": True, "audio_access_authorized": True, "rights_basis": "authorized"})
        with self.assertRaisesRegex(ValueError, "audio fallback is forbidden"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_youtube_accepts_public_anonymous_access_without_attestation(self, _dns):
        request = youtube_request()
        validated = resolve_request.validate_request(request)
        self.assertEqual(validated["youtube_access_basis"], "public-anonymous")

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_stale_concrete_source_set_is_rejected(self, _dns):
        request = copy.deepcopy(BASE)
        request["source_context"]["source_set_version"] = "1.9.0-youtube-scenario-completeness"
        with self.assertRaisesRegex(ValueError, "does not match current toolkit source set"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_public_repo_does_not_require_request_acknowledgement(self, _dns):
        request = youtube_request()
        with patch.dict(resolve_request.os.environ, {"GITHUB_REPOSITORY_VISIBILITY": "public"}):
            validated = resolve_request.validate_request(request)
        self.assertFalse(validated["public_request_acknowledged"])

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_public_repo_allows_task_scoped_analysis_content(self, _dns):
        request = youtube_request()
        request["analysis_content_allowed"] = True
        with patch.dict(resolve_request.os.environ, {"GITHUB_REPOSITORY_VISIBILITY": "public"}):
            validated = resolve_request.validate_request(request)
        self.assertTrue(validated["analysis_content_allowed"])
        self.assertFalse(validated["reuse_allowed"])

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_bounded_comment_budget_is_enforced(self, _dns):
        request = youtube_request()
        request["youtube"].update({"include_comments": True, "max_items": 100, "max_comments": "500"})
        with self.assertRaisesRegex(ValueError, "comment budget"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_all_comments_is_limited_to_five_items(self, _dns):
        request = youtube_request()
        request["youtube"].update({"include_comments": True, "allow_unbounded": True, "max_items": 6, "max_comments": "all"})
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_knowledge_comment_selection_requires_goal_and_owner(self, _dns):
        request = youtube_request()
        request["youtube"].update({"include_comments": True, "comment_selection": "knowledge"})
        request["knowledge_context"] = {"goal": "", "target_owner": "seo"}
        with self.assertRaisesRegex(ValueError, "knowledge_context.goal"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_channel_streams_is_supported(self, _dns):
        request = youtube_request("channel_streams", "https://www.youtube.com/@example")
        validated = resolve_request.validate_request(request)
        self.assertEqual(validated["youtube"]["scope"], "channel_streams")


if __name__ == "__main__":
    unittest.main()
