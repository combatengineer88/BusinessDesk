"""Unit tests for safe complete Python runtime update archives."""
import tempfile
from pathlib import Path
import unittest
import zipfile
from release_layout import valid_release_names,inspect_release

class ReleaseLayoutTests(unittest.TestCase):
    def test_accepts_complete_onedir(self):
        self.assertTrue(valid_release_names(['PhoenixLedger.exe','_internal/python312.dll','_internal/PIL/_imaging.pyd']))
    def test_rejects_missing_dll(self):
        self.assertFalse(valid_release_names(['PhoenixLedger.exe']))
    def test_rejects_sources_and_traversal(self):
        self.assertFalse(valid_release_names(['businessdesk.py','PhoenixLedger.exe','_internal/python312.dll']))
        self.assertFalse(valid_release_names(['PhoenixLedger.exe','_internal/python312.dll','_internal/../../../bad.exe']))
    def test_rejects_backslash_paths(self):
        self.assertFalse(valid_release_names(['PhoenixLedger.exe','_internal\\python312.dll']))
    def test_rejects_duplicate_zip_entries(self):
        self.assertFalse(valid_release_names(['PhoenixLedger.exe','PhoenixLedger.exe','_internal/python312.dll']))
    def test_inspect_valid_and_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('PhoenixLedger.exe',b'MZ'+bytes(110_000))
                z.writestr('_internal/python312.dll',b'MZ'+bytes(10))
                z.writestr('_internal/vcruntime140.dll',b'MZ')
            self.assertEqual(inspect_release(path),3)
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('PhoenixLedger.exe',b'MZ'+bytes(110_000))
            with self.assertRaises(ValueError):inspect_release(path)

if __name__=='__main__':unittest.main()
