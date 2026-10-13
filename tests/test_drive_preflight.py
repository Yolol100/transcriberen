"""Readonly Drive preflight unit contract."""
from scripts.drive_preflight import DrivePreflightError, verify_inventory, EXPECTED_BYTES, ZIP_MIME
import unittest

class ContractTests(unittest.TestCase):
    def test_unexpected_file_count_fails_closed(self):
        with self.assertRaises(DrivePreflightError):
            verify_inventory([])
