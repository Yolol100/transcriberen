import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from knowledge_analysis.corpus import CorpusError, Video, sha256
from knowledge_analysis.routing import load_master_routing, apply_master_routing


def make_master(path, *, route="design", title="Design Lesson", comment_count="1"):
    out = io.StringIO()
    fields = ["video_id", "channel", "title", "date", "domain_routes",
              "source_authority", "authority_status", "comment_count"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerow({"video_id": "ABCDEFGHIJK", "channel": "DesignCourse",
                     "title": title, "date": "2026-10-13",
                     "domain_routes": route, "source_authority": "expert_creator",
                     "authority_status": "verified", "comment_count": comment_count})
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("YouTube_Video_Routing_Index_2026-10-03.csv", out.getvalue())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def video():
    transcript = "Some useful information about design methods."
    return Video("ABCDEFGHIJK", "Design Lesson", "DesignCourse", "20261013",
                 "https://www.youtube.com/watch?v=ABCDEFGHIJK", "unknown", (),
                 transcript, ("Helpful comment",), sha256(transcript), "ok", "shard")


class MasterRoutingTests(unittest.TestCase):
    def test_pinned_master_supplies_correct_classification_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            digest = make_master(path)
            item = video()
            updated = apply_master_routing(item, load_master_routing(path, digest))
            self.assertEqual(updated.routes, ("design",))
            self.assertEqual(updated.authority, "expert_creator")
            self.assertEqual(updated.transcript, item.transcript)
            self.assertEqual(updated.comments, item.comments)

    def test_old_master_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            make_master(path)
            with self.assertRaisesRegex(CorpusError, "SHA-256 mismatch"):
                load_master_routing(path, "0" * 64)

    def test_missing_video_or_wrong_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            digest = make_master(path, title="Other video")
            with self.assertRaisesRegex(CorpusError, "identity mismatch"):
                apply_master_routing(video(), load_master_routing(path, digest))
            missing = Video(**{**video().__dict__, "video_id": "LMNOPQRSTUV"})
            with self.assertRaisesRegex(CorpusError, "absent"):
                apply_master_routing(missing, load_master_routing(path, digest))

    def test_count_and_route_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            digest = make_master(path, comment_count="2")
            with self.assertRaisesRegex(CorpusError, "comment count mismatch"):
                apply_master_routing(video(), load_master_routing(path, digest))
            digest = make_master(path, route="design||leads")
            with self.assertRaisesRegex(CorpusError, "domain routes"):
                load_master_routing(path, digest)

    def test_not_silently_assume_unverified_is_official(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            digest = make_master(path)
            with zipfile.ZipFile(path, "r") as source:
                data = source.read("YouTube_Video_Routing_Index_2026-10-03.csv").decode()
            data = data.replace("expert_creator,verified", ",unverified_supplemental")
            with zipfile.ZipFile(path, "w") as target:
                target.writestr("YouTube_Video_Routing_Index_2026-10-03.csv", data)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(apply_master_routing(video(), load_master_routing(path, digest)).authority,
                             "unverified_supplemental")


if __name__ == "__main__":
    unittest.main()
