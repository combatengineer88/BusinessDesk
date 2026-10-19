"""Regression tests: template migration, independent persistence, export, and preview."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from document_templates import defaults, load_template, save_template, reset_template, render_document, validate


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.database=sqlite3.connect(':memory:')
        self.database.row_factory=sqlite3.Row
        self.database.execute('PRAGMA foreign_keys=ON')
        self.database.executescript('''
          CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,address TEXT,email TEXT);
          CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT,address TEXT,email TEXT);
          CREATE TABLE documents(id INTEGER PRIMARY KEY,kind TEXT,customer_id INTEGER,created TEXT,
             status TEXT,subtotal INTEGER,tax INTEGER,total INTEGER,notes TEXT);
          CREATE TABLE document_items(id INTEGER PRIMARY KEY,document_id INTEGER,description TEXT,
             qty INTEGER,unit_price INTEGER,line_total INTEGER);
          CREATE TABLE purchase_orders(id INTEGER PRIMARY KEY,supplier_id INTEGER,ordered_on TEXT,status TEXT,
             notes TEXT,total INTEGER);
          CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT);
          CREATE TABLE po_items(id INTEGER PRIMARY KEY,po_id INTEGER,product_id INTEGER,qty INTEGER,unit_cost INTEGER);
          INSERT INTO settings VALUES('business_name','Example Business');
          INSERT INTO settings VALUES('business_address','15 Oak Street');
          INSERT INTO customers VALUES(1,'Smith & Sons','Main Street','smith@example.org');
          INSERT INTO suppliers VALUES(1,'Acme Supplies','Industrial Boulevard','vendor@example.org');
          INSERT INTO products VALUES(1,'Laser Engraved Mug');
          INSERT INTO documents VALUES(1,'Estimate',1,'2026-10-19','Open',2500,137,2637,'Custom colors & engraving');
          INSERT INTO documents VALUES(2,'Invoice',1,'2026-10-19','Open',2500,137,2637,'Pay after delivery');
          INSERT INTO document_items VALUES(1,1,'A <B> sample',2,1250,2500);
          INSERT INTO document_items VALUES(2,2,'A <B> sample',2,1250,2500);
          INSERT INTO purchase_orders VALUES(1,1,'2026-10-19','Open','Ship carefully',1800);
          INSERT INTO po_items VALUES(1,1,1,2,900);
        ''')
        self.temp=tempfile.TemporaryDirectory()

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_defaults_are_backward_compatible_and_independent(self):
        self.assertEqual(load_template(self.database,'Invoice')['heading'],'INVOICE')
        self.assertEqual(load_template(self.database,'PO')['recipient_label'],'Supplier')
        config=defaults('Estimate');config['accent_color']='#BB2233';config['heading']='CUSTOM QUOTE'
        save_template(self.database,'Estimate',config)
        self.assertEqual(load_template(self.database,'Estimate')['heading'],'CUSTOM QUOTE')
        self.assertEqual(load_template(self.database,'Invoice')['accent_color'],'#183653')
        self.assertIsNone(self.database.execute('SELECT 1 FROM settings WHERE key=?',('document_template_invoice',)).fetchone())
        reset_template(self.database,'Estimate')
        self.assertEqual(load_template(self.database,'Estimate')['heading'],'ESTIMATE')

    def test_rejects_bad_data(self):
        with self.assertRaises(ValueError):validate('Estimate',{'accent_color':'#abc'})
        with self.assertRaises(ValueError):validate('Invoice',{'layout':'Unexpected'})
        with self.assertRaises(ValueError):validate('Invoice',{'footer':'x'*1600})
        with self.assertRaises(ValueError):validate('PO',{'unknown':'x'})
        with self.assertRaises(ValueError):validate('PO',{'show_logo':'no'})

    def test_all_three_document_types_render(self):
        for kind,rid in [('Estimate',1),('Invoice',2),('PO',1)]:
            output=Path(self.temp.name)/(kind+'.pdf')
            render_document(self.database,kind,rid,output)
            data=output.read_bytes()
            self.assertTrue(data.startswith(b'%PDF-'))
            self.assertGreater(len(data),1400)

    def test_layout_and_print_options_render(self):
        for kind,rid in [('Estimate',1),('Invoice',2),('PO',1)]:
            for layout in ('Modern','Compact'):
                config=defaults(kind)
                config.update(layout=layout,page_size='A4',font='Times-Roman',show_logo=False,
                              terms='Prices are valid only with written confirmation.',
                              footer='TDZIGNS LLC — Thank you',accent_color='#1F6580')
                output=Path(self.temp.name)/(f'{kind}_{layout}.pdf')
                render_document(self.database,kind,rid,output,template_override=config)
                self.assertGreater(output.stat().st_size,1400)

    def test_preview_uses_no_business_rows(self):
        before=self.database.total_changes
        output=Path(self.temp.name)/'preview.pdf'
        config=defaults('PO');config['heading']='VENDOR ORDER'
        render_document(self.database,'PO',0,output,template_override=config,preview=True)
        self.assertTrue(output.read_bytes().startswith(b'%PDF-'))
        self.assertEqual(before,self.database.total_changes)

    def test_existing_invoice_kind_safety(self):
        with self.assertRaises(ValueError):render_document(self.database,'Invoice',1,Path(self.temp.name)/'bad.pdf')
        with self.assertRaises(ValueError):render_document(self.database,'PO',999,Path(self.temp.name)/'bad2.pdf')

if __name__=='__main__':unittest.main()
