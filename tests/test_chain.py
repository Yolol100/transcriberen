"""Regression tests for one-request, sequential 500-video batch handoff."""
import unittest
from scripts.chain import decide, ChainError


class BatchChainTests(unittest.TestCase):
    def inventory(self, total, batch):
        return {"status": "inventory_only",
                "total_unique_videos_in_supplied_corpus": total,
                "actual_batch_count": min(500, total - (batch - 1) * 500)}

    def test_current_library_volume_is_38_batches(self):
        plans = [decide(self.inventory(18875, i), i, "all") for i in range(1, 39)]
        self.assertEqual([x["next_batch"] for x in plans[:-1]], list(range(2, 39)))
        self.assertIsNone(plans[-1]["next_batch"])
        self.assertEqual(plans[-1]["current_batch_videos"], 375)
        self.assertEqual(sum(x["current_batch_videos"] for x in plans), 18875)
        self.assertEqual({x["total_batches"] for x in plans}, {38})

    def test_single_video_single_batch_terminates(self):
        result = decide(self.inventory(1, 1), 1, "all")
        self.assertIsNone(result["next_batch"])
        self.assertTrue(result["terminal"])

    def test_original_single_batch_modes_never_chain(self):
        for mode in ("inventory", "slice", "batch"):
            with self.subTest(mode=mode):
                self.assertIsNone(decide(self.inventory(18875, 1), 1, mode)["next_batch"])

    def test_mismatched_inventory_is_fatal(self):
        broken = self.inventory(18875, 38)
        broken["actual_batch_count"] = 500
        with self.assertRaisesRegex(ChainError, "inconsistent"):
            decide(broken, 38, "all")

    def test_out_of_range_and_invalid_inputs_fail_closed(self):
        with self.assertRaisesRegex(ChainError, "outside corpus"):
            decide(self.inventory(18875, 38), 39, "all")
        with self.assertRaisesRegex(ChainError, "invalid corpus"):
            decide(self.inventory(18875, 1) | {"total_unique_videos_in_supplied_corpus": True}, 1, "all")
        with self.assertRaisesRegex(ChainError, "trusted inventory"):
            decide({"status": "completed", "total_unique_videos_in_supplied_corpus": 18875,
                    "actual_batch_count": 500}, 1, "all")
        with self.assertRaisesRegex(ChainError, "unrecognized"):
            decide(self.inventory(500, 1), 1, "anything")


if __name__ == "__main__":
    unittest.main()
