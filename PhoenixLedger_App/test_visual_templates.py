"""Freeform template regression tests; exercises real PDF render and record isolation."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from visual_templates import default_layout, validate, save, load, reset, render, node, sample_data


class VisualTemplateTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.executescript('''
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,address TEXT,email TEXT);
            CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT,address TEXT,email TEXT);
            CREATE TABLE documents(id INTEGER PRIMARY KEY,kind TEXT,customer_id INTEGER,created TEXT,
               status TEXT,subtotal INTEGER,tax INTEGER,total INTEGER,notes TEXT);
            CREATE TABLE document_items(id INTEGER PRIMARY KEY,document_id INTEGER,description TEXT,
               qty INTEGER,unit_price INTEGER,line_total INTEGER);
            CREATE TABLE purchase_orders(id INTEGER PRIMARY KEY,supplier_id INTEGER,ordered_on TEXT,status TEXT,notes TEXT,total INTEGER);
            CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE po_items(id INTEGER PRIMARY KEY,po_id INTEGER,product_id INTEGER,qty INTEGER,unit_cost INTEGER);
            INSERT INTO settings VALUES('business_name','TDZIGNS LLC');
            INSERT INTO settings VALUES('business_address','10 Main Street');
            INSERT INTO customers VALUES(1,'Customer A','500 Elm Street','a@example.com');
            INSERT INTO suppliers VALUES(1,'Supplier B','11 Factory Road','b@example.com');
            INSERT INTO products VALUES(1,'Large Widget');
            INSERT INTO documents VALUES(1,'Estimate',1,'2026-10-19','Open',1800,99,1899,'Estimate note');
            INSERT INTO documents VALUES(2,'Invoice',1,'2026-10-19','Open',1800,99,1899,'Invoice note');
            INSERT INTO document_items VALUES(1,1,'Example Product',2,900,1800);
            INSERT INTO document_items VALUES(2,2,'Example Product',2,900,1800);
            INSERT INTO purchase_orders VALUES(1,1,'2026-10-19','Open','Order note',1700);
            INSERT INTO po_items VALUES(1,1,1,2,850);
        ''')
        self.files=tempfile.TemporaryDirectory()

    def tearDown(self):self.db.close();self.files.cleanup()

    def test_three_types_independent(self):
        for kind in ('Estimate','Invoice','PO'):
            self.assertIsNone(load(self.db,kind))
            layout=default_layout(kind);validate(kind,layout)
            layout['objects'].append(node('section',50,700,290,42,'Your Custom Section\n{{date}}'))
            save(self.db,kind,layout)
            self.assertEqual(load(self.db,kind)['objects'][-1]['type'],'section')
        est=load(self.db,'Estimate');est['accent']='#CA1455';save(self.db,'Estimate',est)
        self.assertNotEqual(load(self.db,'PO')['accent'],'#CA1455')
        reset(self.db,'Estimate');self.assertIsNone(load(self.db,'Estimate'))

    def test_validation_rejects_invalid(self):
        layout=default_layout('Invoice')
        layout['objects'][0]['x']=-1
        with self.assertRaises(ValueError):validate('Invoice',layout)
        layout=default_layout('Invoice')
        layout['objects'].append(dict(layout['objects'][0]))
        with self.assertRaises(ValueError):validate('Invoice',layout)
        layout=default_layout('PO')
        layout['objects'].append(node('items',42,310,500,140))
        with self.assertRaises(ValueError):validate('PO',layout)
        layout=default_layout('Estimate')
        layout['objects'][2]['text']='A'*3000
        with self.assertRaises(ValueError):validate('Estimate',layout)

    def test_real_document_pdf_all_types(self):
        for kind,index in [('Estimate',1),('Invoice',2),('PO',1)]:
            template=default_layout(kind)
            save(self.db,kind,template)
            outfile=Path(self.files.name)/(kind+'.pdf')
            render(self.db,kind,index,outfile)
            self.assertGreater(outfile.stat().st_size,1500)
            try:
                import fitz
                with fitz.open(outfile) as pdf:
                    text='\n'.join(p.get_text() for p in pdf)
                    self.assertIn('TDZIGNS LLC',text)
                    self.assertIn('Supplier B' if kind=='PO' else 'Customer A',text)
                    self.assertIn('Example Product' if kind!='PO' else 'Large Widget',text)
                    self.assertIn('$17.00' if kind=='PO' else '$18.99',text)
            except ImportError:pass

    def test_preview_does_not_add_document_rows(self):
        before=self.db.execute('SELECT count(*) FROM documents').fetchone()[0]
        file=Path(self.files.name)/'preview.pdf'
        render(self.db,'Estimate',0,file,layout=default_layout('Estimate'),preview=True)
        self.assertGreater(file.stat().st_size,1500)
        self.assertEqual(before,self.db.execute('SELECT count(*) FROM documents').fetchone()[0])

    def test_long_item_table_multiple_pages_and_total(self):
        for i in range(3,55):
            self.db.execute('INSERT INTO document_items VALUES(?,?,?,2,900,1800)',(i,1,'Long line item '+str(i)))
        output=Path(self.files.name)/'long.pdf'
        render(self.db,'Estimate',1,output,layout=default_layout('Estimate'))
        try:
            import fitz
            with fitz.open(output) as pdf:
                self.assertGreaterEqual(len(pdf),4)
                alltext='\n'.join(page.get_text() for page in pdf)
                self.assertIn('Long line item 54',alltext)
                self.assertIn('$18.99',alltext)
        except ImportError:pass


if __name__=='__main__':unittest.main()
