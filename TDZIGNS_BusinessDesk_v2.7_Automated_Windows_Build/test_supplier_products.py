"""Regression tests for v2.9.3 supplier-product assignments and purchase-order filtering."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Avoid using the user's production database during tests.
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='businessdesk_supplier_test_')
from core_v1 import connect
from businessdesk import schema
from excel_import import mapping, parse, import_rows, read_excel
from supplier_catalog import lookup_supplier_id, products_for_supplier, create_supplier_po


class SupplierProductsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        # Simulate a database created by an older version of BusinessDesk.
        self.db.executescript('''
            CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT,phone TEXT,address TEXT);
            CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,email TEXT,phone TEXT,address TEXT,notes TEXT);
            CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,
                description TEXT DEFAULT '',price INTEGER NOT NULL,cost INTEGER NOT NULL,qty INTEGER NOT NULL);
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,password TEXT,role TEXT);
            CREATE TABLE documents(id INTEGER PRIMARY KEY,kind TEXT,customer_id INTEGER,created TEXT,status TEXT,
                subtotal INTEGER,tax INTEGER,total INTEGER,notes TEXT,created_by INTEGER);
            CREATE TABLE document_items(id INTEGER PRIMARY KEY,document_id INTEGER,product_id INTEGER,description TEXT,
                qty INTEGER,unit_price INTEGER,line_total INTEGER);
            CREATE TABLE payments(id INTEGER PRIMARY KEY,document_id INTEGER,paid_on TEXT,amount INTEGER,method TEXT);
            CREATE TABLE expenses(id INTEGER PRIMARY KEY,spent_on TEXT,category TEXT,vendor TEXT,description TEXT,amount INTEGER);
        ''')
        self.db.execute("INSERT INTO suppliers(id,name) VALUES(1,'Alpha Supply'),(2,'Beta Wholesale')")
        self.db.execute("INSERT INTO products(id,sku,name,price,cost,qty) VALUES(1,'LEGACY','Existing Widget',1200,400,7)")
        schema(self.db)
    def tearDown(self):
        self.db.close()

    def test_migration_preserves_existing_products_and_is_repeatable(self):
        self.assertIsNone(self.db.execute("SELECT supplier_id FROM products WHERE sku='LEGACY'").fetchone()[0])
        schema(self.db)
        self.assertEqual(sum(1 for r in self.db.execute('PRAGMA table_info(products)') if r['name']=='supplier_id'),1)
        self.assertEqual(self.db.execute("SELECT qty FROM products WHERE sku='LEGACY'").fetchone()[0],7)

    def test_supplier_assignment_filters_catalog(self):
        self.db.execute("UPDATE products SET supplier_id=1 WHERE sku='LEGACY'")
        rows=[(2,parse('products',{'sku':'NEW','name':'New Product','price':'24.99',
                                         'cost':'11.00','qty':'12','supplier':'Beta Wholesale'}))]
        self.assertEqual(import_rows(self.db,'products',rows),(1,0,0))
        self.assertEqual([r['sku'] for r in products_for_supplier(self.db,1)],['LEGACY'])
        self.assertEqual([r['sku'] for r in products_for_supplier(self.db,2)],['NEW'])

    def test_excel_supplier_header_and_case_insensitive_lookup(self):
        header=mapping(['SKU','Product Name','Price','Vendor Name'],'products')
        self.assertEqual(header['supplier'],3)
        self.assertEqual(lookup_supplier_id(self.db,'alpha SUPPLY'),1)
        self.assertIsNone(lookup_supplier_id(self.db,''))

    def test_excel_import_saves_association_and_preserves_on_blank_update(self):
        rows=[(2,parse('products',{'sku':'SKU-2','name':'Supplied Widget','price':'19.50',
                                         'cost':'9','supplier':'Alpha Supply'}))]
        self.assertEqual(import_rows(self.db,'products',rows),(1,0,0))
        old=self.db.execute("SELECT supplier_id FROM products WHERE sku='SKU-2'").fetchone()[0]
        self.assertEqual(old,1)
        rows=[(2,parse('products',{'sku':'SKU-2','name':'Updated Widget','price':'20',
                                         'supplier':''}))]
        self.assertEqual(import_rows(self.db,'products',rows,'update'),(0,1,0))
        self.assertEqual(self.db.execute("SELECT supplier_id FROM products WHERE sku='SKU-2'").fetchone()[0],1)
        rows=[(2,parse('products',{'sku':'SKU-2','name':'Updated Widget','price':'20',
                                         'supplier':'Beta Wholesale'}))]
        import_rows(self.db,'products',rows,'update')
        self.assertEqual(self.db.execute("SELECT supplier_id FROM products WHERE sku='SKU-2'").fetchone()[0],2)

    def test_unknown_supplier_fails_atomic_import(self):
        rows=[(2,parse('products',{'sku':'WORKS','name':'Widget','price':'1','supplier':'Alpha Supply'})),
              (3,parse('products',{'sku':'BAD','name':'Something','price':'3','supplier':'Not Found'}))]
        with self.assertRaisesRegex(ValueError,'Excel row 3'):
            import_rows(self.db,'products',rows)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM products WHERE sku IN ('WORKS','BAD')").fetchone()[0],0)

    def test_duplicate_supplier_names_not_silently_mapped(self):
        self.db.execute("INSERT INTO suppliers(name) VALUES('alpha supply')")
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            lookup_supplier_id(self.db,'Alpha Supply')

    def test_po_only_for_correct_supplier(self):
        with self.db:
            self.db.execute('UPDATE products SET supplier_id=1 WHERE id=1')
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty,supplier_id) VALUES('BETA','Beta Item',1200,800,5,2)")
        new_id=self.db.execute("SELECT id FROM products WHERE sku='BETA'").fetchone()[0]
        with self.assertRaisesRegex(ValueError,'not assigned'):
            create_supplier_po(self.db,1,'Wrong supplier',[(new_id,2,500)],'2026-10-17')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)
        po_id=create_supplier_po(self.db,1,'Please deliver',[(1,3,475)],'2026-10-17')
        saved=self.db.execute('SELECT supplier_id,total,notes FROM purchase_orders WHERE id=?',(po_id,)).fetchone()
        self.assertEqual(tuple(saved),(1,1425,'Please deliver'))
        self.assertEqual(tuple(self.db.execute('SELECT qty,unit_cost FROM po_items WHERE po_id=?',(po_id,)).fetchone()),(3,475))
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],7)  # no stock until received

    def test_reject_invalid_po_items(self):
        self.db.execute('UPDATE products SET supplier_id=1 WHERE id=1')
        for items in ([(1,0,400)],[(1,1,-2)],[(1,1,500),(1,2,500)]):
            with self.subTest(items=items),self.assertRaises(ValueError):
                create_supplier_po(self.db,1,'',items)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_real_xlsx_round_trip(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'products.xlsx'
            wb=Workbook();ws=wb.active
            ws.append(['SKU','Name','Price','Cost','Qty','Supplier'])
            ws.append(['EXCEL-1','Excel Widget','8.99',4.5,10,'Alpha Supply'])
            wb.save(file)
            records,errors,sheet=read_excel(file,'products')
            self.assertEqual(errors,[])
            self.assertEqual(records[0][1]['supplier'],'Alpha Supply')
            self.assertEqual(import_rows(self.db,'products',records),(1,0,0))
            self.assertEqual(self.db.execute('SELECT supplier_id FROM products WHERE sku=?',('EXCEL-1',)).fetchone()[0],1)

if __name__=='__main__':
    unittest.main(verbosity=2)
