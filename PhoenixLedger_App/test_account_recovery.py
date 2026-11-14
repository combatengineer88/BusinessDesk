import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

TMP=tempfile.TemporaryDirectory(prefix='phoenix_test_recovery_')
os.environ['LOCALAPPDATA']=TMP.name
from core_v1 import connect, hashed, verify
from account_recovery import create_schema, generate_code, has_code, lookup_by_code, reset_with_code, backup_database


class AccountRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT, password TEXT,role TEXT)')
        self.db.execute('CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT)')
        self.db.execute('INSERT INTO users(id,username,password,role) VALUES(1,?,?,?)',('owner',hashed('original-password'), 'admin'))
        self.db.execute('INSERT INTO customers(name) VALUES(?)',('Test Customer',))
        self.db.commit()
        create_schema(self.db)
        self.tmp=tempfile.TemporaryDirectory(prefix='phoenix_recovery_files_')
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def test_code_stored_hash_not_plaintext(self):
        code=generate_code(self.db,1)
        self.assertTrue(has_code(self.db,1))
        stored=self.db.execute('SELECT secret_hash FROM account_recovery').fetchone()[0]
        self.assertNotIn(code.replace('-',''),stored)
        self.assertEqual(lookup_by_code(self.db,code),(1,'owner'))
        self.assertEqual(lookup_by_code(self.db,code.lower().replace('-',' ')),(1,'owner'))
    def test_reset_consumes_code_and_preserves_business_data(self):
        code=generate_code(self.db,1)
        username,archive=reset_with_code(self.db,code,'a_new_secret_0123',self.tmp.name)
        self.assertEqual(username,'owner')
        self.assertTrue(Path(archive).is_file())
        old=sqlite3.connect(archive)
        try:
            self.assertTrue(verify('original-password',old.execute('SELECT password FROM users WHERE id=1').fetchone()[0]))
        finally:old.close()
        self.assertTrue(verify('a_new_secret_0123',self.db.execute('SELECT password FROM users').fetchone()[0]))
        self.assertEqual(self.db.execute('SELECT name FROM customers').fetchone()[0],'Test Customer')
        self.assertIsNone(lookup_by_code(self.db,code))
        with self.assertRaises(ValueError):reset_with_code(self.db,code,'1234567890abcdef',self.tmp.name)
    def test_bad_code_no_change(self):
        code=generate_code(self.db,1)
        old=self.db.execute('SELECT password FROM users').fetchone()[0]
        with self.assertRaises(ValueError):reset_with_code(self.db,'NOPE-SHOULD-FAIL','0123456789aaaa',self.tmp.name)
        self.assertEqual(old,self.db.execute('SELECT password FROM users').fetchone()[0])
        self.assertIsNotNone(lookup_by_code(self.db,code))
    def test_bad_password_no_change(self):
        code=generate_code(self.db,1)
        with self.assertRaises(ValueError):reset_with_code(self.db,code,'short',self.tmp.name)
        self.assertIsNotNone(lookup_by_code(self.db,code))
    def test_nonexistent_user(self):
        with self.assertRaises(ValueError):generate_code(self.db,999)
    def test_reissue_invalidates_old_code(self):
        old=generate_code(self.db,1)
        new=generate_code(self.db,1)
        self.assertIsNone(lookup_by_code(self.db,old))
        self.assertEqual(lookup_by_code(self.db,new),(1,'owner'))
    def test_recovery_schema_migrates_legacy_users(self):
        self.db.execute('DROP TABLE account_recovery')
        create_schema(self.db)
        self.assertFalse(has_code(self.db,1))
        self.assertEqual(self.db.execute('SELECT name FROM customers').fetchone()[0],'Test Customer')


if __name__=='__main__':unittest.main()
