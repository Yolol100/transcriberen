import unittest
from scripts.drive_slice10_checkpoint import prior_records, slot
from scripts.drive_pilot_result import MASTER_SHA,MODEL_SHA,PilotError
from scripts.drive_slice10_result import PURPOSE

def seed():
    return {'schema_version':'1.0','purpose':PURPOSE,'source_master_sha256':MASTER_SHA,'batch':1,'slice':0,'slice_size':10,'status':'awaiting_review','reviews':None}

class ResumeChecks(unittest.TestCase):
    def test_initial_seed(self):
        self.assertEqual(prior_records(seed()),[])
    def test_existing_complete_must_not_be_overwritten(self):
        x=seed();x['status']='ai_reviewed_pending_independent_verification'
        with self.assertRaises(PilotError):prior_records(x)
    def test_wrong_master_sha_rejected(self):
        x=seed();x['source_master_sha256']='0'*64
        with self.assertRaises(PilotError):prior_records(x)
    def test_unpinned_prior_model_rejected(self):
        x=seed();x.update(status='partial_private_checkpoint',model_sha256='0'*64,reviews=[])
        with self.assertRaises(PilotError):prior_records(x)
    def test_empty_checkpoint_allowed(self):
        x=seed();x.update(status='partial_private_checkpoint',model_sha256=MODEL_SHA,reviews=[])
        self.assertEqual(prior_records(x),[])
    def test_duplicate_reviews_rejected(self):
        x=seed();v={'video_id':'abcdefghijk','model_sha256':MODEL_SHA,'policy_version':'knowledge-review-v5','auto_promoted':False}
        x.update(status='partial_private_checkpoint',model_sha256=MODEL_SHA,reviews=[v,v])
        with self.assertRaises(PilotError):prior_records(x)
    def test_final_result_requires_exact_verified_ten_video_checkpoint(self):
        from scripts.drive_slice10_result import validate_final_checkpoint
        saved = [
            {'video_id': ('%011d' % n), 'model_sha256': MODEL_SHA,
             'policy_version': 'knowledge-review-v5', 'auto_promoted': False}
            for n in range(10)
        ]
        item = seed()
        item.update(status='partial_private_checkpoint', model_sha256=MODEL_SHA, reviews=saved)
        self.assertEqual(validate_final_checkpoint(item, list(saved)), 10)
        with self.assertRaisesRegex(PilotError, 'incomplete_private_checkpoint'):
            validate_final_checkpoint(item, saved[:-1])
        tampered = [dict(x) for x in saved]
        tampered[3]['policy_version'] = 'forged-policy'
        with self.assertRaisesRegex(PilotError, 'checkpoint_disagrees'):
            validate_final_checkpoint(item, tampered)
        item['status'] = 'awaiting_review'
        with self.assertRaises(PilotError):
            validate_final_checkpoint(item, saved)

    def test_invalid_folder_rejected(self):
        with self.assertRaises(PilotError):slot('bad/folder','dummy')
