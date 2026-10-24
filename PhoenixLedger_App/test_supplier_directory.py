"""Supplier directory, Excel import, and header-background regression tests."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='phoenixledger_supplier_directory_')
from businessdesk import schema
from supplier_management import ensure_schema, save_supplier, search_suppliers
from excel_import import mapping, parse, import_rows, read_excel
import core_v1


class SupplierDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch.object(core_v1, 'DB', Path(self.tmp.name)/'test.db'):
            self.db=core_v1.connect()
        schema(self.db)
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_fields_added_to_legacy_database(self):
        self.assertTrue(set(('contact_name','website','city','state','zip_code','notes')) <=
                        {r[1] for r in self.db.execute('PRAGMA table_info(suppliers)')})
        ensure_schema(self.db)
        self.assertEqual(sum(1 for r in self.db.execute('PRAGMA table_info(suppliers)') if r[1]=='city'),1)

    def test_insert_edit_preserves_product_and_po_links(self):
        sid=save_supplier(self.db,{'name':'North Supply','contact_name':'Dana','city':'Milwaukee','state':'WI','zip_code':'53202'})
        with self.db:
            self.db.execute('INSERT INTO products(sku,name,price,cost,qty,supplier_id) VALUES(?,?,?,?,?,?)',('ABC','Wrench',1000,500,3,sid))
            self.db.execute("INSERT INTO purchase_orders(supplier_id,ordered_on,total) VALUES(?,?,?)",(sid,'2026-10-20',500))
        self.assertEqual(len(search_suppliers(self.db,'north')),1)
        self.assertEqual(search_suppliers(self.db,'north')[0]['product_count'],1)
        self.assertEqual(search_suppliers(self.db,'north')[0]['po_count'],1)
        save_supplier(self.db,{'name':'North Supply Renamed','contact_name':'Dana B','email':'dana@example.com','city':'Watertown','state':'WI','zip_code':'53094'},sid)
        self.assertEqual(self.db.execute('SELECT supplier_id FROM products WHERE sku=?',('ABC',)).fetchone()[0],sid)
        self.assertEqual(self.db.execute('SELECT supplier_id FROM purchase_orders').fetchone()[0],sid)
        self.assertEqual(self.db.execute('SELECT zip_code FROM suppliers WHERE id=?',(sid,)).fetchone()[0],'53094')
        self.assertEqual(len(search_suppliers(self.db,'watertown')),1)

    def test_duplicate_supplier_name_rejected(self):
        sid=save_supplier(self.db,{'name':'Central Supply'})
        with self.assertRaisesRegex(ValueError,'already exists'):
            save_supplier(self.db,{'name':'CENTRAL SUPPLY'})
        sid2=save_supplier(self.db,{'name':'Other Supply'})
        with self.assertRaisesRegex(ValueError,'already uses'):
            save_supplier(self.db,{'name':'central supply'},sid2)
        self.assertNotEqual(sid,sid2)

    def test_excel_mapping_and_partial_updates(self):
        cols=mapping(['Supplier Name','Primary Contact','Street Address','City','State','ZIP Code','Website','Notes'],'suppliers')
        self.assertEqual(cols['contact_name'],1)
        self.assertEqual(cols['zip_code'],5)
        item=parse('suppliers',{'name':'Cedar Parts','contact_name':'Jordan','city':'Boston','zip_code':'02110','website':'https://example.test'})
        self.assertEqual(import_rows(self.db,'suppliers',[(2,item)]),(1,0,0))
        patch_row=parse('suppliers',{'name':'Cedar Parts','phone':'555-0100'})
        self.assertEqual(import_rows(self.db,'suppliers',[(2,patch_row)],'update'),(0,1,0))
        saved=self.db.execute('SELECT * FROM suppliers WHERE name=?',('Cedar Parts',)).fetchone()
        self.assertEqual(saved['zip_code'],'02110')
        self.assertEqual(saved['phone'],'555-0100')
        self.assertEqual(saved['contact_name'],'Jordan')

    def test_real_xlsx_import_and_skip(self):
        from openpyxl import Workbook
        file=Path(self.tmp.name)/'suppliers.xlsx'
        wb=Workbook();ws=wb.active
        ws.append(['Supplier Name','Contact Name','City','State','ZIP Code'])
        ws.append(['Oak Distribution','Alex','Boston','MA','02110'])
        wb.save(file)
        records, errors, _=read_excel(file,'suppliers')
        self.assertEqual(errors,[])
        self.assertEqual(import_rows(self.db,'suppliers',records),(1,0,0))
        self.assertEqual(import_rows(self.db,'suppliers',records,'skip'),(0,0,1))
        self.assertEqual(self.db.execute('SELECT zip_code FROM suppliers').fetchone()[0],'02110')

    def test_bulk_import_duplicate_is_atomic(self):
        rows=[(2,parse('suppliers',{'name':'Same Co'})),(3,parse('suppliers',{'name':'same co'}))]
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            import_rows(self.db,'suppliers',rows)
        self.assertEqual(self.db.execute('SELECT count(*) FROM suppliers').fetchone()[0],0)

    def test_search_treats_sql_wildcards_literally(self):
        save_supplier(self.db,{'name':'A_1 Supplier'})
        save_supplier(self.db,{'name':'Alpha Supply'})
        self.assertEqual([r['name'] for r in search_suppliers(self.db,'_')],['A_1 Supplier'])


class HeaderAppearanceTests(unittest.TestCase):
    def test_header_image_uses_matching_banner_background(self):
        try:
            import tkinter as tk
            from modern_theme import SLATE,apply
            root=tk.Tk();root.withdraw()
        except tk.TclError:
            self.skipTest('No GUI display available')
            return
        try:
            apply(root)
            header=tk.Frame(root,bg=SLATE)
            image=tk.PhotoImage(file=str(Path(__file__).parent/'phoenixledger_icon.png'))
            label=tk.Label(header,image=image,bg=SLATE,bd=0,highlightthickness=0,relief='flat')
            self.assertEqual(label.cget('bg'),SLATE)
            self.assertEqual(int(label.cget('highlightthickness')),0)
            self.assertEqual(int(label.cget('bd')),0)
        finally:
            root.destroy()


if __name__=='__main__':
    unittest.main(verbosity=2)
