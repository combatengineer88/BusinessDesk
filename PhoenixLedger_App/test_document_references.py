"""PDF date/reference placement for invoice, estimate, PO and saved visual templates."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fitz
from document_templates import render_document, defaults
from visual_templates import default_layout, render as render_visual, save as save_visual, load as load_visual


class DocumentReferences(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
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
          INSERT INTO settings VALUES('business_name','PhoenixLedger Reference Test');
          INSERT INTO customers VALUES(1,'Customer Example','10 Main St','customer@example.test');
          INSERT INTO suppliers VALUES(1,'Supplier Example','20 Main St','supplier@example.test');
          INSERT INTO products VALUES(1,'Widget');
          INSERT INTO documents VALUES(17,'Estimate',1,'2026-10-20','Open',4000,0,4000,'');
          INSERT INTO documents VALUES(35,'Invoice',1,'2026-10-20','Open',4000,0,4000,'');
          INSERT INTO document_items VALUES(1,17,'Widget',2,2000,4000);
          INSERT INTO document_items VALUES(2,35,'Widget',2,2000,4000);
          INSERT INTO purchase_orders VALUES(52,1,'2026-10-20','Open','',3000);
          INSERT INTO po_items VALUES(1,52,1,2,1500);
        ''')

    def tearDown(self):self.db.close();self.work.cleanup()

    def verify(self, file, reference):
        with fitz.open(file) as pdf:
            blocks=pdf[0].get_text('dict')['blocks']
            words=[(span['text'],fitz.Rect(span['bbox'])) for b in blocks if 'lines' in b
                   for ln in b['lines'] for span in ln['spans']]
            reference_boxes=[box for text,box in words if reference in text]
            date_boxes=[box for text,box in words if 'Date: 2026-10-20' in text]
            self.assertEqual(len(reference_boxes),1,words)
            self.assertEqual(len(date_boxes),1,words)
            self.assertLess(abs(reference_boxes[0].x0-date_boxes[0].x0),55,words)
            self.assertLess(abs(reference_boxes[0].y0-date_boxes[0].y0),40,words)

    def test_classic_date_reference_group(self):
        for kind,id_,ref in [('Estimate',17,'Estimate #: 17'),('Invoice',35,'Invoice #: 35'),('PO',52,'PO #: 52')]:
            for layout in ('Modern','Compact'):
                with self.subTest(kind=kind,layout=layout):
                    out=Path(self.work.name)/f'classic_{kind}_{layout}.pdf'
                    template=defaults(kind);template['layout']=layout;template['show_logo']=False
                    render_document(self.db,kind,id_,out,template_override=template)
                    self.verify(out,ref)

    def test_visual_default_date_reference_group(self):
        for kind,id_,ref in [('Estimate',17,'Estimate #: 17'),('Invoice',35,'Invoice #: 35'),('PO',52,'PO #: 52')]:
            with self.subTest(kind=kind):
                out=Path(self.work.name)/f'visual_{kind}.pdf'
                render_visual(self.db,kind,id_,out,layout=default_layout(kind))
                self.verify(out,ref)

    def test_saved_previous_default_moves_number_from_title(self):
        template=default_layout('Invoice')
        box=next(o for o in template['objects'] if o['type']=='section' and 'DOCUMENT DETAILS' in o['text'])
        box['text']='DOCUMENT DETAILS\nDate: {{date}}';box['h']=69
        from visual_templates import node
        template['objects'].insert(5,node('field',430,166,140,25,'#{{document_number}}',14,True,'#2563EB',align='right'))
        save_visual(self.db,'Invoice',template)
        original=self.db.execute('SELECT value FROM settings WHERE key=?',('visual_template_invoice',)).fetchone()[0]
        updated=load_visual(self.db,'Invoice')
        self.assertIn('document_reference_label',next(o for o in updated['objects'] if o['type']=='section' and 'DOCUMENT DETAILS' in o['text'])['text'])
        # Compatibility upgrade is in-memory only; the saved record is untouched until explicitly edited.
        self.assertEqual(original,self.db.execute('SELECT value FROM settings WHERE key=?',('visual_template_invoice',)).fetchone()[0])
        out=Path(self.work.name)/'legacy_invoice.pdf'
        render_visual(self.db,'Invoice',35,out)
        self.verify(out,'Invoice #: 35')


if __name__=='__main__':unittest.main()
