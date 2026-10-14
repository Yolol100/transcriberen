"""Negative-path regression gates for the private v15 real Qwen smoke test."""
from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.drive_corpus_fetch import PrivateSourceFailure, download_one, get_sources
from scripts.drive_pilot_result import (
    PilotError, PURPOSE, MODEL_SHA, MASTER_SHA, validate_seed,
    validate_private_review, write_existing,
)


def seed():
    return {'schema_version': '1.0', 'purpose': PURPOSE,
            'source_master_sha256': MASTER_SHA, 'batch': 1, 'slice': 0,
            'slice_size': 1, 'status': 'awaiting_review', 'review': None}


class LivePilotRegressions(unittest.TestCase):
    def test_seed_accepted(self):
        self.assertIsNone(validate_seed(seed()))

    def test_seed_cannot_overwrite_existing_review(self):
        for changes in ({'status': 'ai_reviewed_pending_independent_verification'},
                        {'review': {'claims': []}}, {'source_master_sha256': '0' * 64},
                        {'slice_size': 20}, {'batch': 2}):
            s = seed(); s.update(changes)
            with self.subTest(changes=changes), self.assertRaises(PilotError):
                validate_seed(s)

    def test_write_rejects_malformed_folder_before_network(self):
        with self.assertRaises(PilotError):
            write_existing('../wrong', 'x', seed())

    def test_real_review_requires_file_model_and_sources(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PilotError):
                validate_private_review(Path(td), Path(td), Path(td)/'missing.gguf', '1234')

    def test_download_rejects_existing_local_file(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / 'sample.zip'
            dest.write_bytes(b'existing')
            with self.assertRaises(PrivateSourceFailure):
                download_one('safe-test-fileid', dest, 1, 'secret')
            self.assertEqual(dest.read_bytes(), b'existing')

    def test_download_stops_before_oversize(self):
        class Resp(io.BytesIO):
            status = 200
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / 'sample.zip'
            with patch('scripts.drive_corpus_fetch.urlopen', return_value=Resp(b'123456')):
                with self.assertRaises(PrivateSourceFailure):
                    download_one('safe-test-fileid', dest, 5, 'secret')
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_suffix('.zip.partial').exists())

    def test_fetch_fail_closed_on_missing_token(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PrivateSourceFailure):
                get_sources('safe-folder-id', '', Path(td) / 'v15')

    def test_constants_match_immutable_qwen_weights(self):
        self.assertEqual(len(MODEL_SHA), 64)
        self.assertEqual(len(MASTER_SHA), 64)


if __name__ == '__main__':
    unittest.main()
