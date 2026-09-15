import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("external_corpus", ROOT / "scripts" / "validate_external_corpus.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExternalCorpusTests(unittest.TestCase):
    def test_contract_keeps_import_separate_from_network_acquisition(self):
        contract = json.loads((ROOT / "external-corpus-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["schema_version"], "1.0")
        self.assertEqual(contract["capability_id"], "external-youtube-caption-corpus-intake")
        self.assertEqual(contract["runtime_target"], "local-file-intake-only")
        boundaries = " ".join(contract["boundaries"]).casefold()
        self.assertIn("does not perform youtube search", boundaries)
        self.assertIn("evidence/discovery", boundaries)
        for key in ("owner_skill", "project_id", "source_set_version"):
            self.assertNotIn(key, contract)

    def build_fixture(self, root, *, status="partial", tamper_manifest=False, missing_transcript=False):
        payload = root / "OUTPUT"
        payload.mkdir()
        run_id = "20260915_test"
        run_dir = payload / f"run_{run_id}"
        items_dir = run_dir / "items"
        items_dir.mkdir(parents=True)
        transcript = items_dir / "20260915_Test_Video_abcDEF12345.txt"
        transcript.write_text("verified caption text\n", encoding="utf-8")
        rel = "items/20260915_Test_Video_abcDEF12345.txt"
        (run_dir / "RUN-SHA256.txt").write_text(f"{sha(transcript)}  {rel}\n", encoding="utf-8")
        partial_reasons = ["subtitle:xyz:empty"] if status == "partial" else []
        manifest = {
            "schema_version": 2,
            "version": "1.3.3",
            "run_id": run_id,
            "run_status": status,
            "updated_at": "2026-09-15T00:00:00+02:00",
            "date_start": "20260101",
            "date_end": "20261231",
            "channels": [{"Url": "https://www.youtube.com/@Test", "Category": "programming", "Name": "Test"}],
            "discovered": 1,
            "saved": 1,
            "partial_reasons": partial_reasons,
            "items": [{
                "video_id": "abcDEF12345",
                "channel": "Test",
                "category": "programming",
                "type": "Video",
                "title": "Fixture",
                "upload_date": "20260915",
                "url": "https://www.youtube.com/watch?v=abcDEF12345",
                "status": "saved",
                "reason": "",
                "transcript_language": "en",
                "transcript_kind": "subtitles",
                "output_file": rel,
            }],
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        inner_zip = payload / f"WORDPRESS_YOUTUBE_2026_{run_id}.zip"
        with zipfile.ZipFile(inner_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(transcript, rel)
            zf.write(manifest_path, "manifest.json")
        receipt = {
            "schema_version": 1,
            "version": "1.3.3",
            "run_id": run_id,
            "terminal_status": status,
            "exit_code": 4 if status == "partial" else 0,
            "created_at": "2026-09-15T00:01:00+02:00",
            "result_zip": inner_zip.name,
            "result_zip_sha256": sha(inner_zip),
            "manifest_sha256": sha(manifest_path),
            "saved": 1,
            "already_saved": 0,
            "discovered": 1,
            "partial_reasons": partial_reasons,
        }
        receipt_path = payload / f"RESULT-RECEIPT_{run_id}.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        (payload / "RESULT-RECEIPT_LATEST.json").write_text(json.dumps(receipt), encoding="utf-8")
        if tamper_manifest:
            manifest_path.write_text(manifest_path.read_text() + " ", encoding="utf-8")
        if missing_transcript:
            transcript.unlink()
        outer = root / "OUTPUT.zip"
        with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in payload.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())
        return outer

    def test_partial_corpus_is_valid_evidence_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = self.build_fixture(root)
            out = root / "out"
            result = m.validate_external_corpus(source, out)
            self.assertEqual(result["collector"]["terminal_status"], "partial")
            self.assertEqual(result["knowledge_status"], "evidence_only")
            self.assertFalse(result["promotion"]["automatic_project_truth"])
            self.assertTrue((out / "candidate-index.json").is_file())

    def test_success_without_partial_reasons_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = self.build_fixture(root, status="success")
            result = m.validate_external_corpus(source, root / "out")
            self.assertEqual(result["collector"]["terminal_status"], "success")

    def test_manifest_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = self.build_fixture(root, tamper_manifest=True)
            with self.assertRaisesRegex(m.IntakeError, "manifest SHA-256"):
                m.validate_external_corpus(source, root / "out")

    def test_missing_saved_transcript_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = self.build_fixture(root, missing_transcript=True)
            with self.assertRaisesRegex(m.IntakeError, "saved transcript missing"):
                m.validate_external_corpus(source, root / "out")

    def test_zip_path_traversal_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            outer = root / "evil.zip"
            with zipfile.ZipFile(outer, "w") as zf:
                zf.writestr("../escape.txt", "no")
            with self.assertRaisesRegex(m.IntakeError, "unsafe archive member"):
                m.validate_external_corpus(outer, root / "out")


if __name__ == "__main__":
    unittest.main()
