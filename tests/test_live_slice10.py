import tempfile
import unittest
from pathlib import Path
from scripts.drive_slice10_result import FILE_NAME, PURPOSE, PilotError, validate_seed, validate_slice, store
from scripts.drive_preflight import MASTER_SHA

class Slice10Tests(unittest.TestCase):
    def sample(self):
        return {'schema_version':'1.0','purpose':PURPOSE,'source_master_sha256':MASTER_SHA,
                'status':'awaiting_review','batch':1,'slice':0,'slice_size':10,'reviews':None}
    def test_seed(self):
        self.assertIsNone(validate_seed(self.sample()))
    def test_already_reviewed_not_overwritten(self):
        s=self.sample();s['status']='ai_reviewed_pending_independent_verification'
        with self.assertRaises(PilotError):validate_seed(s)
    def test_no_existing_review_data(self):
        s=self.sample();s['reviews']=[{}]
        with self.assertRaises(PilotError):validate_seed(s)
    def test_unexpected_batch(self):
        s=self.sample();s['batch']=2
        with self.assertRaises(PilotError):validate_seed(s)
    def test_source_sha_not_changeable(self):
        s=self.sample();s['source_master_sha256']='0'*64
        with self.assertRaises(PilotError):validate_seed(s)
    def test_scope_requires_existing_model(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PilotError):
                validate_slice(Path(d),Path(d),Path(d)/'absent.gguf','1234')
    def test_writer_cannot_target_arbitrary_folder(self):
        with self.assertRaises(PilotError):store('../bad','test',self.sample())
    def test_exact_result_name(self):
        self.assertEqual(FILE_NAME,'qwen-b001-s00-10.json')
