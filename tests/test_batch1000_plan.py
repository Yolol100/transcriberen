import unittest
from scripts.batch1000_plan import BatchPlanError, plan_1000

class BatchGrouping(unittest.TestCase):
    def test_exact_groups(self):
        groups = plan_1000()
        self.assertEqual(len(groups), 19)
        self.assertEqual(sum(item["video_count"] for item in groups), 18875)
        self.assertEqual(groups[-1]["video_count"], 875)
        self.assertEqual(groups[-1]["existing_500_video_batches"][-1]["video_count"], 375)
        self.assertEqual(groups[-1]["existing_500_video_batches"][-1]["internal_batch"], 38)

    def test_unexpected_count_is_rejected(self):
        with self.assertRaises(BatchPlanError):
            plan_1000(18874)
