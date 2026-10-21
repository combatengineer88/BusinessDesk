"""PhoenixLedger v2.9.10 PO create/edit/save regression tests."""
import sqlite3
import unittest
from datetime import date

from supplier_catalog import create_supplier_po,update_supplier_po


class PurchaseOrderEditingTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE suppliers(id INTEGER PRIMARY KEY,name TEXT NOT NULL);
            CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT,name TEXT,cost INTEGER,supplier_id INTEGER REFERENCES suppliers(id));
            CREATE TABLE purchase_orders(id INTEGER PRIMARY KEY,supplier_id INTEGER REFERENCES suppliers(id),ordered_on TEXT,status TEXT DEFAULT 'Open',notes TEXT,total INTEGER);
            CREATE TABLE po_items(id INTEGER PRIMARY KEY,po_id INTEGER REFERENCES purchase_orders(id),product_id INTEGER REFERENCES products(id),qty INTEGER,unit_cost INTEGER);
        ''')
        self.db.executemany('INSERT INTO suppliers(id,name) VALUES(?,?)',[(1,'Acme'),(2,'Beta')])
        self.db.executemany('INSERT INTO products(id,sku,name,cost,supplier_id) VALUES(?,?,?,?,?)',[
            (1,'AA','Widgets',1000,1),(2,'BB','Labels',400,1),(3,'CC','Other supplier',250,2)])
        self.db.commit()

    def tearDown(self):self.db.close()

    def test_can_save_po_and_adjust_qty_and_cost(self):
        po=create_supplier_po(self.db,1,'Please ship',[(1,2,1000)],'2026-10-19')
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],2000)
        updated=update_supplier_po(self.db,po,'Rush order',[(1,5,975),(2,3,240)])
        self.assertEqual(updated,po)
        self.assertEqual(tuple(self.db.execute('SELECT notes,total FROM purchase_orders WHERE id=?',(po,)).fetchone()),('Rush order',5595))
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT product_id,qty,unit_cost FROM po_items WHERE po_id=? ORDER BY product_id',(po,))],[(1,5,975),(2,3,240)])

    def test_existing_lines_can_be_removed_and_replaced(self):
        po=create_supplier_po(self.db,1,'',[(1,2,1000),(2,1,200)])
        update_supplier_po(self.db,po,'after edit',[(2,9,300)])
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT product_id,qty,unit_cost FROM po_items WHERE po_id=?',(po,))],[(2,9,300)])
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],2700)

    def test_mismatch_rejected_without_partial_save(self):
        po=create_supplier_po(self.db,1,'original',[(1,2,1000)])
        before=self.db.execute('SELECT notes,total FROM purchase_orders WHERE id=?',(po,)).fetchone()
        with self.assertRaisesRegex(ValueError,'not assigned'):
            update_supplier_po(self.db,po,'bad edit',[(1,5,500),(3,9,250)])
        self.assertEqual(tuple(self.db.execute('SELECT notes,total FROM purchase_orders WHERE id=?',(po,)).fetchone()),tuple(before))
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT qty,unit_cost FROM po_items WHERE po_id=?',(po,))],[(2,1000)])

    def test_cannot_change_received_po_or_accounting(self):
        po=create_supplier_po(self.db,1,'Original',[(1,2,400)])
        self.db.execute("UPDATE purchase_orders SET status='Received' WHERE id=?",(po,))
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'Only open purchase orders'):
            update_supplier_po(self.db,po,'illegitimate',[(1,8,300)])
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],800)

    def test_reassigned_original_is_editable_but_new_line_rejected(self):
        po=create_supplier_po(self.db,1,'',[(1,1,1000)])
        self.db.execute('UPDATE products SET supplier_id=2 WHERE id=1')
        update_supplier_po(self.db,po,'',[(1,3,800)])
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],2400)
        with self.assertRaisesRegex(ValueError,'not assigned'):
            update_supplier_po(self.db,po,'',[(1,3,800),(3,1,200)])

    def test_validation_rejects_duplicate_and_invalid(self):
        po=create_supplier_po(self.db,1,'',[(1,1,1000)])
        for lines in ([(1,0,100)],[(1,-2,100)],[(1,2,-1)],[(1,1,200),(1,1,300)],[]):
            with self.subTest(lines=lines),self.assertRaises(ValueError):
                update_supplier_po(self.db,po,'',lines)
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],1000)

    def test_transaction_rolls_back_if_second_insert_fails(self):
        po=create_supplier_po(self.db,1,'Original',[(1,2,1000)])
        self.db.execute('''CREATE TRIGGER reject_second_po_line BEFORE INSERT ON po_items
                           WHEN NEW.product_id=2 BEGIN SELECT RAISE(FAIL,'simulated database failure'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            update_supplier_po(self.db,po,'Should rollback',[(1,1,100),(2,2,200)])
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],2000)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT product_id,qty,unit_cost FROM po_items WHERE po_id=?',(po,))],[(1,2,1000)])


if __name__=='__main__':unittest.main(verbosity=2)
