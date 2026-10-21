"""Release metadata and installer-file sanity checks; no Windows dependencies."""
from pathlib import Path
import tempfile
import unittest
from installer_assets import select_update_asset, validate_setup_file

VERSION='2.9.7'
BASE=f'https://github.com/combatengineer88/BusinessDesk/releases/download/v{VERSION}/'
SHA='a'*64

class InstallerAssetsTests(unittest.TestCase):
    def manifest(self):
        return {
            'version':VERSION,'url':BASE+f'PhoenixLedger_{VERSION}.zip',
            'sha256':SHA,'installer_url':BASE+f'PhoenixLedger_Setup_{VERSION}.exe',
            'installer_sha256':'B'*64
        }
    def test_prefers_setup(self):
        v,u,h,kind=select_update_asset(self.manifest(),BASE.removesuffix('v2.9.7/'))
        self.assertEqual((v,kind,h),(VERSION,'setup','b'*64))
        self.assertTrue(u.endswith('.exe'))
    def test_legacy_release_uses_zip(self):
        manifest=self.manifest()
        del manifest['installer_url'],manifest['installer_sha256']
        self.assertEqual(select_update_asset(manifest)[-1],'zip')
    def test_rejects_bad_or_untrusted_download(self):
        manifest=self.manifest()
        manifest['installer_url']='https://example.com/PhoenixLedger_Setup_2.9.7.exe'
        with self.assertRaises(ValueError):select_update_asset(manifest,BASE.removesuffix('v2.9.7/'))
    def test_rejects_bad_hash(self):
        manifest=self.manifest();manifest['installer_sha256']='bad'
        with self.assertRaises(ValueError):select_update_asset(manifest)
    def test_rejects_mismatched_filename(self):
        manifest=self.manifest();manifest['installer_url']=BASE+'PhoenixLedger_Setup_2.9.6.exe'
        with self.assertRaises(ValueError):select_update_asset(manifest)
    def test_setup_requires_expected_filename_mz_and_size(self):
        with tempfile.TemporaryDirectory() as td:
            valid=Path(td)/'PhoenixLedger_Setup_2.9.7.exe'
            valid.write_bytes(b'MZ'+b'0'*1_000_010)
            self.assertTrue(validate_setup_file(valid))
            valid.write_bytes(b'BAD'+b'0'*1_000_010)
            with self.assertRaises(ValueError):validate_setup_file(valid)

if __name__=='__main__':unittest.main()
