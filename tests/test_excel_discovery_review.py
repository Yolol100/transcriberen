"""Synthetic-only regression tests for misleading name matches and date flags."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from knowledge_analysis.excel_quality import (
    classify_entity, compare_date_flags, inspect_mentions,
)
from scripts.audit_excel_discovery import main


class EntityEvidenceTests(unittest.TestCase):
    def assert_supported(self, entity, text, title=""):
        x = classify_entity(entity, text, title)
        self.assertEqual(x.gate, "CONTEXT_PRESENT_UNVERIFIED")
        self.assertFalse(x.auto_promoted)

    def assert_ambiguous(self, entity, text, title=""):
        x = classify_entity(entity, text, title)
        self.assertEqual(x.gate, "AMBIGUOUS_NEEDS_REVIEW")
        self.assertFalse(x.auto_promoted)

    def test_microsoft_clarity_vs_normal_clarity(self):
        self.assert_ambiguous("Microsoft Clarity", "Hopefully this brings clarity on your choices.")
        self.assert_supported("Microsoft Clarity", "Review Microsoft Clarity heatmaps and session recordings.")

    def test_title_alone_does_not_count_as_evidence(self):
        self.assert_ambiguous("Microsoft Clarity", "This lesson teaches how to focus.", "Microsoft Clarity tutorial")

    def test_rag_not_a_company_layoff_or_ordinary_rag(self):
        self.assert_ambiguous("RAG", "This rag was left behind after the layoffs.")
        self.assert_supported("RAG", "Use RAG with a vector database for document retrieval.")
        self.assert_supported("RAG", "Retrieval-augmented generation can ground an LLM.")

    def test_zero_to_one_requires_book_context(self):
        self.assert_ambiguous("Zero to One", "Move from zero to one and toggle the flag.")
        self.assert_ambiguous("Zero to One", "Go from zero to one; in chapter 3 we discuss pricing in this masterclass.")
        self.assert_supported("Zero to One", "I read Zero to One by Peter Thiel.")

    def test_the_one_thing_requires_book_context(self):
        self.assert_ambiguous("The ONE Thing", "The one thing I recommend is to review the form.")
        self.assert_supported("The ONE Thing", "The ONE Thing by Gary Keller is a book.")

    def test_astro_vs_generic_and_astra(self):
        self.assert_ambiguous("Astro", "The astrologer says Astro is a nickname.")
        self.assert_supported("Astro", "Use Astro web framework with islands architecture.")
        self.assert_ambiguous("Astro", "Astra is the WordPress theme used here.")

    def test_atomic_book_not_elementor(self):
        self.assert_ambiguous("Atomic Habits", "Elementor Atomic Editor has an atomic habit of reusing widgets.")
        self.assert_supported("Atomic Habits", "I read the book Atomic Habits by James Clear.")

    def test_excel_literal_apostrophe_preserves_leading_dash_video_ids(self):
        rows = [{"Video ID": "'-XXXXXXXXXX", "Bron": "Microsoft Clarity", "Fragment": "Microsoft Clarity heatmaps", "Videotitel": "demo"}]
        self.assertEqual(inspect_mentions(rows)[0]["video_id"], "-XXXXXXXXXX")

    def test_no_auto_promotion_for_export_rows(self):
        rows = [
            {"Video ID": "AAAAAAAAAAA", "Bron": "Microsoft Clarity", "Fragment": "I have clarity on my career", "Videotitel": "job search"},
            {"Video ID": "BBBBBBBBBBB", "Bron": "RAG", "Fragment": "RAG uses vector search and retrieval.", "Videotitel": "intro"},
            {"Video ID": "CCCCCCCCCCC", "Bron": "Other framework", "Fragment": "A real source", "Videotitel": "intro"},
        ]
        result = inspect_mentions(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["gate"], "AMBIGUOUS_NEEDS_REVIEW")
        self.assertEqual(result[1]["gate"], "CONTEXT_PRESENT_UNVERIFIED")
        self.assertTrue(all(x["auto_promoted"] == "false" for x in result))


class DateIntegrityTests(unittest.TestCase):
    @staticmethod
    def make_rows(n=31):
        ids = [f"VID{i:08d}" for i in range(n)]
        excel = [{"Video ID": vid, "Datum": "", "Datum betrouwbaar": "Nee"} for vid in ids]
        raw = [{"video_id": vid, "date": "2025-02-19", "date_verified": "True"} for vid in ids]
        return excel, raw

    def test_all_31_synthetic_conflicts_are_reported_without_rewriting_input(self):
        excel, raw = self.make_rows()
        before_excel, before_raw = repr(excel), repr(raw)
        result = compare_date_flags(excel, raw)
        self.assertEqual(len(result), 31)
        self.assertEqual({x["review"] for x in result}, {"REQUIRES_SOURCE_VERIFICATION_NO_AUTO_CORRECTION"})
        self.assertEqual(repr(excel), before_excel)
        self.assertEqual(repr(raw), before_raw)

    def test_matching_booleans_are_not_conflicts(self):
        excel, raw = self.make_rows(1)
        excel[0]["Datum betrouwbaar"] = "Ja"
        self.assertEqual(compare_date_flags(excel, raw), [])

    def test_duplicate_or_missing_video_ids_fail_closed(self):
        excel, raw = self.make_rows(2)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compare_date_flags(excel + excel[:1], raw)
        with self.assertRaisesRegex(ValueError, "missing"):
            compare_date_flags(excel, raw[:1])
        with self.assertRaisesRegex(ValueError, "Invalid"):
            compare_date_flags([{**excel[0], "Datum betrouwbaar": "unknown"}, excel[1]], raw)

    def test_cli_writes_review_only_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            excel, raw = self.make_rows(2)
            mention = [{"Video ID": "AAAAAAAAAAA", "Bron": "Zero to One", "Fragment": "from zero to one", "Videotitel": "test"}]
            def write_csv(name, rows):
                path = root / name
                with path.open("w", encoding="utf-8", newline="") as h:
                    w = csv.DictWriter(h, fieldnames=list(rows[0]))
                    w.writeheader();w.writerows(rows)
                return path
            mention_file = write_csv("mentions.csv", mention)
            excel_file = write_csv("excel.csv", excel)
            raw_file = write_csv("raw.csv", raw)
            original = [p.read_bytes() for p in (mention_file, excel_file, raw_file)]
            out = root / "review-output"
            self.assertEqual(main(["--mentions-csv", str(mention_file), "--excel-index-csv", str(excel_file),
                                   "--raw-screening-csv", str(raw_file), "--output-dir", str(out)]), 0)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["date_flag_conflicts"], 2)
            self.assertEqual(summary["reviewed_ambiguous_matches"], 1)
            self.assertEqual(summary["decision"], "EVIDENCE_ONLY_NO_AUTO_PROMOTION")
            self.assertEqual([p.read_bytes() for p in (mention_file, excel_file, raw_file)], original)
            with self.assertRaises(SystemExit):
                main(["--mentions-csv", str(mention_file), "--output-dir", str(out)])


if __name__ == "__main__":
    unittest.main()
