"""Regression tests for v3.4 inventory history, reordering, and scan operations."""
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import sqlite3
import tempfile

import core_v1
from businessdesk import schema
from inventory_management import (ensure_schema,lookup_scan,adjust_stock,update_policy,
    inventory_summary,reorder_recommendations,create_reorder_drafts,approve_reorder_draft,movements)
from supplier_catalog import update_supplier_po
from account_workflows import receive_po,po_lines
from inventory_labels import edit_product_field


class InventoryManagementTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.object(core_v1,'DB',Path(self.temp.name)/'data.db'):
            self.db=core_v1.connect()
        self.addCleanup(self.db.close)
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO suppliers(id,name) VALUES(1,'Supplier One')")
            self.db.execute("INSERT INTO products(id,sku,name,barcode,qty,cost,price,supplier_id) VALUES(1,'SKU1','Shirt','004444',3,750,1500,1)")
            self.db.execute("INSERT INTO products(id,sku,name,barcode,qty,cost,price,supplier_id) VALUES(2,'SKU2','Mug','005555',15,300,800,1)")
            self.db.execute("INSERT INTO products(id,sku,name,barcode,qty,cost,price,supplier_id) VALUES(3,'SKU3','Unassigned','006666',0,200,600,NULL)")

    def test_safe_migration_preserves_balance_and_baselines_once(self):
        original=self.db.execute('SELECT id,qty,cost FROM products ORDER BY id').fetchall()
        initial=self.db.execute('SELECT count(*) FROM inventory_movements').fetchone()[0]
        schema(self.db);ensure_schema(self.db)
        self.assertEqual([tuple(x) for x in original],
                         [tuple(x) for x in self.db.execute('SELECT id,qty,cost FROM products ORDER BY id')])
        self.assertEqual(initial,self.db.execute('SELECT count(*) FROM inventory_movements').fetchone()[0])

    def test_scanner_finds_sku_or_barcode_and_rejects_missing(self):
        self.assertEqual(lookup_scan(self.db,'004444')['id'],1)
        self.assertEqual(lookup_scan(self.db,'sku1')['id'],1)
        with self.assertRaises(ValueError):lookup_scan(self.db,'missing')
        with self.assertRaises(ValueError):lookup_scan(self.db,'')

    def test_adjustments_leave_audited_balance_and_reason(self):
        self.assertEqual(adjust_stock(self.db,1,'Add',8,'Returned stock','operator'),(3,11))
        self.assertEqual(adjust_stock(self.db,1,'Remove',4,'Damaged / scrap','operator'),(11,7))
        self.assertEqual(adjust_stock(self.db,1,'Set',0,'Physical stock count','supervisor'),(7,0))
        recorded=movements(self.db,1)
        self.assertEqual([r['change_qty'] for r in recorded[:3]],[-7,-4,8])
        self.assertEqual(recorded[0]['source'],'scan_adjustment')
        self.assertEqual(recorded[0]['reason'],'Physical stock count')
        self.assertEqual(recorded[0]['actor'],'supervisor')
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],0)
        ctx=self.db.execute('SELECT source FROM inventory_change_context').fetchone()[0]
        self.assertEqual(ctx,'system')

    def test_reject_invalid_and_do_not_log_changes(self):
        count=self.db.execute('SELECT count(*) FROM inventory_movements').fetchone()[0]
        for args in [('Remove',4,'Reason'),('Add',0,'Reason'),('Set',3,'No change'),('Add',2,''),('Add',-3,'Reason')]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                adjust_stock(self.db,1,*args)
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM inventory_movements').fetchone()[0],count)

    def test_legacy_inline_updates_are_audited(self):
        edit_product_field(self.db,1,'qty','24',actor='admin')
        m=movements(self.db,1)[0]
        self.assertEqual((m['old_qty'],m['change_qty'],m['new_qty']),(3,21,24))
        self.assertEqual(m['source'],'manual_edit')
        with self.db:self.db.execute('UPDATE products SET qty=qty-2 WHERE id=1')
        self.assertEqual(movements(self.db,1)[0]['source'],'system')

    def test_nonstocked_items_excluded_and_policy_changes_safe(self):
        self.assertEqual(update_policy(self.db,[1,2],5,25,'made_to_order','Shelf B'),2)
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],3)
        self.assertEqual(self.db.execute('SELECT bin_location FROM products WHERE id=1').fetchone()[0],'Shelf B')
        self.assertNotIn(1,{r['id'] for r in reorder_recommendations(self.db)})
        with self.assertRaises(ValueError):update_policy(self.db,[1],-2,10)
        with self.assertRaises(ValueError):update_policy(self.db,[1],5,3,'other')

    def test_suggestions_group_suppliers_and_prevent_duplicate_drafts(self):
        update_policy(self.db,[1],5,20,'stocked')
        created,missing=create_reorder_drafts(self.db)
        self.assertEqual(len(created),1)
        self.assertEqual(len(missing),1)
        poid=created[0]
        po=self.db.execute('SELECT status,total FROM purchase_orders WHERE id=?',(poid,)).fetchone()
        self.assertEqual(po['status'],'Draft')
        expected=5+20-3
        line=self.db.execute('SELECT product_id,qty,unit_cost FROM po_items WHERE po_id=?',(poid,)).fetchone()
        self.assertEqual(tuple(line),(1,expected,750))
        created_again,missing_again=create_reorder_drafts(self.db)
        self.assertFalse(created_again)
        self.assertEqual(len(missing_again),1)
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],3)
        self.assertFalse(self.db.execute('SELECT 1 FROM journal WHERE source_type="po_receipt"').fetchone())

    def test_draft_must_be_approved_before_receiving_and_stays_editable(self):
        ids,_=create_reorder_drafts(self.db)
        poid=ids[0]
        with self.assertRaisesRegex(ValueError,'already fully received'):
            receive_po(self.db,poid,{po_lines(self.db,poid)[0]['id']:1})
        update_supplier_po(self.db,poid,'Reviewed by owner',[(1,8,650)])
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(poid,)).fetchone()[0],5200)
        approve_reorder_draft(self.db,poid)
        with self.assertRaises(ValueError):approve_reorder_draft(self.db,poid)
        line=po_lines(self.db,poid)[0]
        receipt,status=receive_po(self.db,poid,{line['id']:3})
        self.assertEqual(status,'Partially Received')
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],6)
        movement=movements(self.db,1)[0]
        self.assertEqual(movement['source'],'po_receipt')
        self.assertIn(str(receipt),movement['reason'])

    def test_inventory_summary_counts_and_costs(self):
        stats=inventory_summary(self.db)
        self.assertEqual(stats['count'],3)
        self.assertEqual(stats['out_count'],1)
        self.assertEqual(stats['low_count'],2)
        self.assertEqual(stats['stock_value'],3*750+15*300)

if __name__=='__main__':main()
