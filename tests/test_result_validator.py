import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "validate_result.py"
spec = importlib.util.spec_from_file_location("result_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

DIGESTS = {
    "yt-dlp": "1" * 64,
    "deno": "2" * 64,
    "ffmpeg": "3" * 64,
    "ffprobe": "4" * 64,
}


def base_request():
    return {
        "enabled": True,
        "request_id": "transcribe-test-001",
        "owner": "webactueel-workflow",
        "project_id": "project-transcriberen",
        "url": "https://www.youtube.com/@OpenAI",
        "mode": "auto",
        "language": "auto",
        "max_items": 1,
        "allow_audio_fallback": False,
        "audio_access_authorized": False,
        "reuse_allowed": False,
        "rights_basis": "analysis-only",
        "source_context": {"project_id": "project-transcriberen", "source_set_version": "test"},
    }


def base_provenance(request):
    return {
        "request_sha256": validator.canonical_request_sha256(request),
        "repository_commit": "local",
        "github_run_id": None,
        "github_ref": None,
        "python_version": "3.12.0",
        "python_implementation": "CPython",
        "platform": "test",
        "tool_sha256": dict(DIGESTS),
    }


class ResultValidatorTests(unittest.TestCase):
    def test_collection_contract_accepts_consistent_no_content_result(self):
        request = base_request()
        provenance = base_provenance(request)
        item = {
            "index": 1,
            "video_id": "abcdefghijk",
            "title": "Example",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "source_target": "https://www.youtube.com/@OpenAI/videos",
            "status": "no_usable_captions",
            "detail": "none",
        }
        result = {
            "schema_version": "webactueel-transcription-result/1.0",
            "request_id": request["request_id"],
            "owner": "webactueel-workflow",
            "project_id": "project-transcriberen",
            "source_url": request["url"],
            "requested_mode": "auto",
            "detected_mode": "youtube_collection",
            "language": "auto",
            "evidence_level": "controlled_runtime",
            "reuse_allowed": False,
            "rights_basis": "analysis-only",
            "audio_access_authorized": False,
            "content_sha256": validator.sha256_text(""),
            "content_chars": 0,
            "content_persisted": False,
            "tool_versions": {"yt-dlp": "x", "ffmpeg": "x", "ffprobe": "x", "trafilatura": "2.1.0"},
            "provenance": provenance,
            "source_context": request["source_context"],
            "metadata": {
                "items": [item],
                "collection_targets": ["https://www.youtube.com/@OpenAI/videos"],
                "discovery_targets_attempted": ["https://www.youtube.com/@OpenAI/videos"],
                "discovery_status": "complete",
                "discovery_errors": [],
                "attempted_items": 1,
                "not_attempted_items": 0,
                "captions_collected": 0,
                "captions_unavailable": 1,
                "caption_access_errors": 0,
                "processing_errors": 0,
                "not_attempted_source_access_blocked": 0,
                "scan_status": "no_usable_captions",
            },
        }
        register = {
            "schema_version": "webactueel-source-register/1.0",
            "request_id": request["request_id"],
            "request_sha256": provenance["request_sha256"],
            "repository_commit": "local",
            "sources": [item],
        }
        handoff = {
            "schema_version": "webactueel-knowledge-handoff/1.0",
            "request_id": request["request_id"],
            "promotion_status": "rights_review_required",
            "content_available": False,
            "content_path": None,
            "source_register_path": "source-register.json",
            "request_sha256": provenance["request_sha256"],
            "repository_commit": "local",
            "source_items": [item],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            results = root / "results"
            results.mkdir()
            request_path = root / "resolved-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result_path = results / "result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            (results / "source-register.json").write_text(json.dumps(register), encoding="utf-8")
            (results / "knowledge-handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            with patch.object(validator, "current_tool_digests", return_value=dict(DIGESTS)), \
                 patch.dict(os.environ, {"GITHUB_WORKSPACE": str(root), "GITHUB_ACTIONS": "false"}, clear=False):
                self.assertEqual(validator.validate_result(result_path, request_path), [])

    def test_persisted_content_hash_tampering_is_detected(self):
        request = base_request()
        request["url"] = "https://example.com/article"
        request["mode"] = "article"
        request["reuse_allowed"] = True
        request["rights_basis"] = "publisher explicitly permits reuse"
        provenance = base_provenance(request)
        result = {
            "schema_version": "webactueel-transcription-result/1.0",
            "request_id": request["request_id"],
            "owner": "webactueel-workflow",
            "project_id": "project-transcriberen",
            "source_url": request["url"],
            "requested_mode": "article",
            "detected_mode": "article",
            "language": "auto",
            "evidence_level": "controlled_runtime",
            "reuse_allowed": True,
            "rights_basis": request["rights_basis"],
            "audio_access_authorized": False,
            "content_sha256": validator.sha256_text("expected\n"),
            "content_chars": len("expected\n"),
            "content_persisted": True,
            "tool_versions": {"yt-dlp": "x", "ffmpeg": "x", "ffprobe": "x", "trafilatura": "2.1.0"},
            "provenance": provenance,
            "source_context": request["source_context"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            results = root / "results"
            results.mkdir()
            request_path = root / "resolved-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result_path = results / "result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            (results / "content.md").write_text("tampered-long\n", encoding="utf-8")
            with patch.object(validator, "current_tool_digests", return_value=dict(DIGESTS)), \
                 patch.dict(os.environ, {"GITHUB_WORKSPACE": str(root), "GITHUB_ACTIONS": "false"}, clear=False):
                errors = validator.validate_result(result_path, request_path)
            self.assertIn("persisted content sha256 mismatch", errors)
            self.assertIn("persisted content chars mismatch", errors)

    def test_request_provenance_mismatch_is_detected(self):
        request = base_request()
        provenance = base_provenance(request)
        provenance["request_sha256"] = "0" * 64
        result = {
            "schema_version": "webactueel-transcription-result/1.0",
            "request_id": request["request_id"],
            "owner": "webactueel-workflow",
            "project_id": "project-transcriberen",
            "source_url": request["url"],
            "requested_mode": "auto",
            "detected_mode": "youtube_collection",
            "language": "auto",
            "evidence_level": "controlled_runtime",
            "reuse_allowed": False,
            "rights_basis": "analysis-only",
            "audio_access_authorized": False,
            "content_sha256": validator.sha256_text(""),
            "content_chars": 0,
            "content_persisted": False,
            "tool_versions": {"yt-dlp": "x", "ffmpeg": "x", "ffprobe": "x", "trafilatura": "2.1.0"},
            "provenance": provenance,
            "source_context": request["source_context"],
            "metadata": {
                "items": [{"status": "no_usable_captions"}],
                "collection_targets": [request["url"]],
                "discovery_targets_attempted": [request["url"]],
                "discovery_status": "complete",
                "discovery_errors": [],
                "attempted_items": 1,
                "not_attempted_items": 0,
                "captions_collected": 0,
                "captions_unavailable": 1,
                "caption_access_errors": 0,
                "processing_errors": 0,
                "not_attempted_source_access_blocked": 0,
                "scan_status": "no_usable_captions",
            },
        }
        register = {"schema_version": "webactueel-source-register/1.0", "request_id": request["request_id"], "request_sha256": provenance["request_sha256"], "repository_commit": "local", "sources": result["metadata"]["items"]}
        handoff = {"schema_version": "webactueel-knowledge-handoff/1.0", "request_id": request["request_id"], "promotion_status": "rights_review_required", "content_available": False, "content_path": None, "source_register_path": "source-register.json", "request_sha256": provenance["request_sha256"], "repository_commit": "local", "source_items": result["metadata"]["items"]}
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            results = root / "results"
            results.mkdir()
            request_path = root / "resolved-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result_path = results / "result.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            (results / "source-register.json").write_text(json.dumps(register), encoding="utf-8")
            (results / "knowledge-handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            with patch.object(validator, "current_tool_digests", return_value=dict(DIGESTS)), \
                 patch.dict(os.environ, {"GITHUB_WORKSPACE": str(root), "GITHUB_ACTIONS": "false"}, clear=False):
                errors = validator.validate_result(result_path, request_path)
            self.assertIn("provenance request_sha256", errors)


if __name__ == "__main__":
    unittest.main()
