"""Positive and adversarial comment coverage tests; only synthetic text."""
import copy
import tempfile
import unittest
from pathlib import Path
from knowledge_analysis.corpus import Video, sha256
from knowledge_analysis.review import review_video
from scripts.verify_real_comment_canary import CanaryError, validate_saved_comments

MODEL_SHA="a"*64

class FakeLocalQwen:
    def ask(self, source, text, metadata):
        return {"summary":"synthetic only","claims":[],"uncertainty":"not verified"}

def synthetic_video():
    text="A short, harmless example of source-linked WordPress documentation."
    return Video(
        video_id="ABCDEFGHIJK",title="Synthetic comment sample",channel="Test",
        published_date="20261015",url="https://www.youtube.com/watch?v=ABCDEFGHIJK",
        authority="expert_creator",routes=("wordpressqualityarchitect",),
        transcript=text,
        comments=("How is this configured?","A second question",
                  "Has this been tested?","This helped me."),
        transcript_sha256=sha256(text),comments_status="ok",
        provenance="synthetic-private-source",transcript_hash_claim=sha256(text),
        transcript_hash_status="match",
    )

class RealCommentCanaryUnitTests(unittest.TestCase):
    def fixture(self):
        v=synthetic_video()
        with tempfile.TemporaryDirectory() as directory:
            r=review_video(v,model=FakeLocalQwen(),model_sha256=MODEL_SHA,
                           out_dir=Path(directory),chunk_size=5600)
        return v,r

    def test_all_four_comment_chunks_processed(self):
        v,r=self.fixture()
        x=validate_saved_comments(v,r,MODEL_SHA)
        self.assertEqual(x["stored_comments_checked"],4)
        self.assertEqual(x["comment_segments_checked"],4)
        self.assertEqual(x["transcript_segments_checked"],1)
        self.assertFalse(x["source_promoted"])

    def test_missing_comment_chunk_fails_closed(self):
        v,r=self.fixture()
        bad=copy.deepcopy(r)
        bad["chunks"]=[c for c in bad["chunks"]
                       if not (c["source"]=="comment" and c["comment_index"]==2)]
        with self.assertRaisesRegex(CanaryError,"incomplete_or_unanchored"):
            validate_saved_comments(v,bad,MODEL_SHA)

    def test_false_completeness_flag_fails(self):
        v,r=self.fixture()
        bad=copy.deepcopy(r);bad["comments_read_completely"]=False
        with self.assertRaisesRegex(CanaryError,"incomplete_or_unanchored"):
            validate_saved_comments(v,bad,MODEL_SHA)

    def test_zero_comment_sample_is_not_positive(self):
        v,r=self.fixture()
        v=Video(**{**v.__dict__,"comments":()})
        with self.assertRaisesRegex(CanaryError,"positive_comment_sample_unavailable"):
            validate_saved_comments(v,r,MODEL_SHA)

    def test_model_or_source_tampering_fails(self):
        v,r=self.fixture()
        with self.assertRaisesRegex(CanaryError,"incomplete_or_unanchored"):
            validate_saved_comments(v,r,"b"*64)
        v=Video(**{**v.__dict__,"comments":v.comments[:-1]+("altered",)})
        with self.assertRaisesRegex(CanaryError,"incomplete_or_unanchored"):
            validate_saved_comments(v,r,MODEL_SHA)

    def test_forged_human_approval_fails(self):
        v,r=self.fixture()
        bad=copy.deepcopy(r);bad["human_qa_approved"]=True
        with self.assertRaisesRegex(CanaryError,"incomplete_or_unanchored"):
            validate_saved_comments(v,bad,MODEL_SHA)

if __name__=="__main__":
    unittest.main()
