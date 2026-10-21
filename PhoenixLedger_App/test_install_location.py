"""Regression coverage for ephemeral ZIP-extracted executable paths."""
import unittest
from install_location import choose_install_target,is_temporary_install

TEMP=r'C:\Users\example\AppData\Local\Temp'
LOCAL=r'C:\Users\example\AppData\Local'
STABLE=r'C:\Users\example\AppData\Local\Programs\PhoenixLedger\PhoenixLedger.exe'

class InstallLocationTests(unittest.TestCase):
    def test_diagnostic_zip_extraction_is_not_installation(self):
        old=r'C:\Users\example\AppData\Local\Temp\4f48ff_PhoenixLedger_2.9.3.zip.a81\PhoenixLedger.exe'
        self.assertTrue(is_temporary_install(old,TEMP))
        self.assertEqual(choose_install_target(old,LOCAL,TEMP),(STABLE,True))

    def test_migrates_temp_without_zip_marker(self):
        old=r'C:\Users\example\AppData\Local\Temp\one-off\PhoenixLedger.exe'
        self.assertTrue(is_temporary_install(old,TEMP))

    def test_migrates_permanent_custom_location(self):
        old=r'D:\Tools\PhoenixLedger\PhoenixLedger.exe'
        self.assertEqual(choose_install_target(old,LOCAL,TEMP),(STABLE,True))

    def test_preserves_standard_location(self):
        self.assertEqual(choose_install_target(STABLE,LOCAL,TEMP),(STABLE,False))

    def test_case_insensitive_windows_paths(self):
        old=r'c:\USERS\EXAMPLE\APPDATA\LOCAL\TEMP\FILE.ZIP.X\TDZIGNS_BUSINESSDESK.EXE'
        self.assertEqual(choose_install_target(old,LOCAL,TEMP),(STABLE,True))

    def test_invalid_name_rejected(self):
        with self.assertRaises(ValueError):
            is_temporary_install(r'C:\Temp\not-businessdesk.exe',TEMP)

if __name__=='__main__':unittest.main()
