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
    "rights_basis": "analysis-paraphrase-only",
    "source_context": {"project_id": "project-transcriberen", "source_set_version": "test-source-set"}
}


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
    def test_analysis_artifact_does_not_imply_reuse(self, _dns):
        request = copy.deepcopy(BASE)
        request["analysis_content_allowed"] = True
        validated = resolve_request.validate_request(request)
        self.assertTrue(validated["analysis_content_allowed"])
        self.assertFalse(validated["reuse_allowed"])

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_audio_fallback_requires_explicit_authorization(self, _dns):
        request = copy.deepcopy(BASE)
        request["allow_audio_fallback"] = True
        with self.assertRaisesRegex(ValueError, "audio_access_authorized=true"):
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
        request = copy.deepcopy(BASE)
        request.pop("analysis_content_allowed", None)
        request.update({
            "mode": "youtube", "url": "",
            "youtube": {"scope": "search", "query": "wordpress performance", "year_from": 2025, "year_to": 2026}
        })
        validated = resolve_request.validate_request(request)
        self.assertIsNone(validated["url"])
        self.assertEqual(validated["youtube"]["query"], "wordpress performance")
        self.assertTrue(validated["analysis_content_allowed"])

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_youtube_channel_scope_requires_youtube_host(self, _dns):
        request = copy.deepcopy(BASE)
        request.update({"mode": "youtube", "youtube": {"scope": "channel_all"}})
        with self.assertRaisesRegex(ValueError, "YouTube scope requires"):
            resolve_request.validate_request(request)

    @patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS)
    def test_youtube_disallows_audio_fallback(self, _dns):
        request = copy.deepcopy(BASE)
        request.update({
            "mode": "youtube", "url": "https://www.youtube.com/watch?v=abc",
            "youtube": {"scope": "video"}, "allow_audio_fallback": True,
            "audio_access_authorized": True, "rights_basis": "authorized"
        })
        with self.assertRaisesRegex(ValueError, "audio fallback is forbidden"):
            resolve_request.validate_request(request)

    def test_youtube_comment_all_requires_explicit_unbounded_opt_in(self):
        request = copy.deepcopy(BASE)
        request.update({
            "mode": "youtube", "url": "https://www.youtube.com/watch?v=abc",
            "youtube": {"scope": "video", "include_comments": True, "max_comments": "all"}
        })
        with patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            with self.assertRaisesRegex(ValueError, "allow_unbounded"):
                resolve_request.validate_request(request)

    def test_youtube_comment_all_is_supported_with_explicit_unbounded_opt_in(self):
        request = copy.deepcopy(BASE)
        request.update({
            "mode": "youtube", "url": "https://www.youtube.com/watch?v=abc",
            "youtube": {"scope": "video", "include_comments": True, "max_comments": "all", "allow_unbounded": True}
        })
        with patch.object(resolve_request.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            validated = resolve_request.validate_request(request)
        self.assertEqual(validated["youtube"]["max_comments"], "all")
        self.assertTrue(validated["youtube"]["allow_unbounded"])


if __name__ == "__main__":
    unittest.main()
