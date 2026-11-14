"""Regression tests for product cell edits, barcode PNGs, printable sticker PDFs."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw
from inventory_labels import (ensure_inventory_schema, attach_barcode_png,
    edit_product_field, get_label_products, render_label_sheet, LABEL_FORMATS)


class InventoryLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
           CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,
               name TEXT NOT NULL,description TEXT,barcode TEXT UNIQUE,price INTEGER,
               cost INTEGER,qty INTEGER, image_path TEXT DEFAULT '',supplier_id INTEGER);
           CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT NOT NULL);
           INSERT INTO suppliers(id,name) VALUES (8,'Supplier Eight');
           INSERT INTO products(id,sku,name,barcode,description,price,cost,qty)
             VALUES(1,'T100','Custom Blue T-Shirt','123456789','Blue shirt',2295,800,25);
           INSERT INTO products(id,sku,name,barcode,description,price,cost,qty)
             VALUES(2,'M200','Coffee Mug','112233445566','Mug',1295,420,10);
        ''')
        ensure_inventory_schema(self.db)
        img=Image.new('RGB',(600,120),'white')
        draw=ImageDraw.Draw(img)
        for x in range(10,590,13):draw.rectangle([x,8,x+5,105],fill='black')
        self.png=self.root/'barcode.png'
        img.save(self.png)

    def test_migration_idempotent(self):
        ensure_inventory_schema(self.db)
        cols={x[1] for x in self.db.execute('PRAGMA table_info(products)')}
        self.assertIn('barcode_image_path',cols)
        self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0],2)

    def test_png_attachment_is_owned_and_separate_from_product_photo(self):
        with self.db:self.db.execute("UPDATE products SET image_path='/photos/shirt.jpg' WHERE id=1")
        target=attach_barcode_png(self.db,1,self.png,self.root)
        self.assertTrue(target.is_file())
        self.png.unlink()
        row=self.db.execute('SELECT image_path,barcode_image_path FROM products WHERE id=1').fetchone()
        self.assertEqual(row['image_path'],'/photos/shirt.jpg')
        self.assertEqual(row['barcode_image_path'],str(target))
        self.assertEqual(self.db.execute('SELECT barcode_image_path FROM products WHERE id=2').fetchone()[0],'')

    def test_reject_non_png_even_when_named_png(self):
        fake=self.root/'notreal.png';fake.write_text('not an image')
        with self.assertRaises(ValueError):attach_barcode_png(self.db,1,fake,self.root)
        self.assertEqual(self.db.execute('SELECT barcode_image_path FROM products WHERE id=1').fetchone()[0],'')

    def test_inline_edit_price_stock_supplier_barcode(self):
        self.assertEqual(edit_product_field(self.db,1,'price','$9.95'),995)
        self.assertEqual(edit_product_field(self.db,1,'qty','29'),29)
        self.assertEqual(edit_product_field(self.db,1,'supplier_id',8),8)
        self.assertEqual(edit_product_field(self.db,1,'barcode','ABC123'),'ABC123')
        row=self.db.execute('SELECT * FROM products WHERE id=1').fetchone()
        self.assertEqual((row['price'],row['qty'],row['supplier_id'],row['barcode']),(995,29,8,'ABC123'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0],2)

    def test_invalid_edits_leave_record_intact(self):
        for field,bad in [('qty','2.5'),('qty','-3'),('price','-1'),('name',''),('supplier_id',999),('barcode_image_path','abc')]:
            with self.subTest(field=field,bad=bad):
                with self.assertRaises(ValueError):edit_product_field(self.db,1,field,bad)
        self.assertEqual(self.db.execute('SELECT qty,price,name FROM products WHERE id=1').fetchone()[:],(25,2295,'Custom Blue T-Shirt'))

    def test_duplicate_sku_fails_without_changing_other_product(self):
        with self.assertRaises(sqlite3.IntegrityError):edit_product_field(self.db,1,'sku','M200')
        self.assertEqual(self.db.execute('SELECT sku FROM products WHERE id=1').fetchone()[0],'T100')

    def test_generate_30_up_sticker_page_with_png_and_vector(self):
        attach_barcode_png(self.db,1,self.png,self.root)
        out=self.root/'labels_30.pdf'
        render_label_sheet(self.db,[(1,2),(2,3)],out)
        self.assertTrue(out.exists())
        import fitz
        with fitz.open(out) as pdf:
            self.assertEqual(len(pdf),1)
            self.assertEqual((round(pdf[0].rect.width),round(pdf[0].rect.height)),(612,792))
            body=pdf[0].get_text()
            self.assertEqual(body.count('Custom Blue T-Shirt'),2)
            self.assertEqual(body.count('Coffee Mug'),3)
            self.assertTrue(pdf[0].get_images())

    def test_10_up_partial_sheet_and_more_than_one_page(self):
        import fitz
        fmt=list(LABEL_FORMATS)[1]
        out=self.root/'labels_10.pdf'
        render_label_sheet(self.db,[(2,12)],out,fmt,start_at=4,print_price=False)
        with fitz.open(out) as pdf:
            self.assertEqual(len(pdf),2)
            self.assertEqual(pdf[0].get_text().count('Coffee Mug'),7)
            self.assertEqual(pdf[1].get_text().count('Coffee Mug'),5)
            self.assertNotIn('$12.95',pdf[0].get_text())

    def test_missing_png_uses_1d_generated_barcode(self):
        with self.db:self.db.execute("UPDATE products SET barcode_image_path='/missing.png' WHERE id=2")
        product=get_label_products(self.db,[(2,1)])[0][0]
        self.assertEqual(product['source'],'Code128')
        self.assertTrue(render_label_sheet(self.db,[(2,1)],self.root/'fallback.pdf').exists())

    def test_bad_quantities_and_formats(self):
        for qty in (0,501):
            with self.assertRaises(ValueError):get_label_products(self.db,[(1,qty)])
        with self.assertRaises(ValueError):render_label_sheet(self.db,[(1,1)],self.root/'bad.pdf','Other')
        with self.assertRaises(ValueError):render_label_sheet(self.db,[(1,1)],self.root/'bad.pdf',start_at=31)

if __name__=='__main__':unittest.main()
