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


def make_master(path, *, route="design", title="Design Lesson", comment_count="1", catalog=None):
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
        if catalog is not None:
            archive.writestr("YouTube_Source_Catalog_2026-10-03.json",
                             json.dumps(catalog))
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


    def test_v15_catalog_fixes_stale_unverified_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            make_master(path)
            with zipfile.ZipFile(path) as z:
                data = z.read("YouTube_Video_Routing_Index_2026-10-03.csv").decode()
            data = data.replace("expert_creator,verified", ",unverified_supplemental")
            catalog = {"channels": {"DesignCourse": {
                "authority_status": "verified", "source_authority": "research_publisher"}}}
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("YouTube_Video_Routing_Index_2026-10-03.csv", data)
                z.writestr("YouTube_Source_Catalog_2026-10-03.json", json.dumps(catalog))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            item = apply_master_routing(video(), load_master_routing(path, digest))
            self.assertEqual(item.authority, "research_publisher")
            self.assertEqual(item.transcript, video().transcript)
            self.assertEqual(item.comments, video().comments)

    def test_catalog_unverified_channel_overrides_verified_video_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            catalog = {"channels": {"DesignCourse": {
                "authority_status": "unverified_supplemental",
                "source_authority": None}}}
            digest = make_master(path, catalog=catalog)
            item = apply_master_routing(video(), load_master_routing(path, digest))
            self.assertEqual(item.authority, "unverified_supplemental")

    def test_corrupt_or_missing_catalog_identity_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            for catalog in (
                {"channels": {"Wrong": {"authority_status": "verified",
                                         "source_authority": "expert_creator"}}},
                {"channels": {"DesignCourse": {"authority_status": "verified",
                                              "source_authority": None}}},
                {"channels": {"DesignCourse": {"authority_status": "unknown",
                                              "source_authority": "expert_creator"}}},
            ):
                with self.subTest(catalog=catalog):
                    digest = make_master(path, catalog=catalog)
                    with self.assertRaisesRegex(CorpusError, "catalog"):
                        load_master_routing(path, digest)

    def test_multiple_catalogs_block_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.zip"
            make_master(path)
            with zipfile.ZipFile(path, "a") as z:
                z.writestr("YouTube_Source_Catalog_2026-10-03.json",
                           json.dumps({"channels": {"DesignCourse": {
                               "authority_status": "verified",
                               "source_authority": "expert_creator"}}}))
                z.writestr("YouTube_Source_Catalog_2026-10-04.json",
                           json.dumps({"channels": {"DesignCourse": {
                               "authority_status": "verified",
                               "source_authority": "expert_creator"}}}))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(CorpusError, "ambiguous"):
                load_master_routing(path, digest)

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
