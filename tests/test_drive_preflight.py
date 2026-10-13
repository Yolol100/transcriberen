"""Private Drive inventory regression tests."""
import unittest
from scripts import drive_preflight as d

def valid():
    return [{"id":"safe_test_object_identifier","name":n,"mimeType":d.ZIP_MIME,"size":str(s)} for n,s in d.EXPECTED_BYTES.items()]

class DrivePreflightTests(unittest.TestCase):
    def test_exact_inventory(self):
        r=d.verify_inventory(valid())
        self.assertEqual(r["count"],16)
        self.assertEqual(r["total_bytes"],207414827)
    def test_missing(self):
        with self.assertRaises(d.DrivePreflightError): d.verify_inventory(valid()[:-1])
    def test_duplicate(self):
        a=valid();a[-1]=a[0].copy()
        with self.assertRaises(d.DrivePreflightError): d.verify_inventory(a)
    def test_wrong_size(self):
        a=valid();a[0]["size"]="1"
        with self.assertRaises(d.DrivePreflightError): d.verify_inventory(a)
    def test_wrong_mime(self):
        a=valid();a[0]["mimeType"]="text/plain"
        with self.assertRaises(d.DrivePreflightError): d.verify_inventory(a)
    def test_wrong_id(self):
        a=valid();a[0]["id"]="not valid"
        with self.assertRaises(d.DrivePreflightError): d.verify_inventory(a)
    def test_bad_folder_id(self):
        with self.assertRaises(d.DrivePreflightError): d.list_folder("not valid","test")
