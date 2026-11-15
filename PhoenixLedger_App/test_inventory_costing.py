"""Migration and accounting regression tests for PhoenixLedger v3.5 bulk pricing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core_v1
from businessdesk import schema
from core_v1 import cents
from inventory_costing import (rounded_cents,set_bulk_quote,set_manual_cost,set_price_tier,
    delete_price_tier,quote_for_qty,suggested_order_qty,margin_info,cost_history,update_pack_rules)
from inventory_labels import edit_product_field
from inventory_management import reorder_recommendations,create_reorder_drafts,update_policy,inventory_summary
from account_workflows import po_lines,receive_po


class CostingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.object(core_v1,'DB',Path(self.temp.name)/'db.sqlite'):
            self.db=core_v1.connect()
        self.addCleanup(self.db.close)
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO suppliers(id,name) VALUES(1,'Bulk Supplier')")
            self.db.execute("INSERT INTO products(id,sku,name,price,cost,qty,supplier_id) VALUES(1,'TSHIRT','Black Shirt',1299,450,3,1)")

    def test_quote_recalculates_cost_and_keeps_inventory_basis(self):
        self.assertEqual(rounded_cents(19200,48),400)
        self.assertEqual(set_bulk_quote(self.db,1,48,19200,case_pack_qty=12,min_order_qty=24,actor='admin'),400)
        row=self.db.execute('SELECT reorder_qty,reorder_cost_total,cost,inventory_unit_cost,case_pack_qty,min_order_qty FROM products WHERE id=1').fetchone()
        self.assertEqual(tuple(row),(48,19200,400,450,12,24))
        self.assertEqual(inventory_summary(self.db)['stock_value'],3*450)
        self.assertEqual(cost_history(self.db,1)[0]['change_type'],'bulk_quote')
        self.assertAlmostEqual(margin_info(1299,400)['margin_percent'],69.207,places=2)
        count=self.db.execute('SELECT count(*) FROM product_cost_history').fetchone()[0]
        schema(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM product_cost_history').fetchone()[0],count)

    def test_reorder_quantity_update_recalculates_unit_quote(self):
        set_bulk_quote(self.db,1,48,19200)
        self.assertEqual(edit_product_field(self.db,1,'reorder_qty','24','admin'),24)
        self.assertEqual(self.db.execute('SELECT cost FROM products WHERE id=1').fetchone()[0],800)
        self.assertEqual(edit_product_field(self.db,1,'reorder_cost_total','$216.00','admin'),900)
        row=self.db.execute('SELECT reorder_cost_total,cost FROM products WHERE id=1').fetchone()
        self.assertEqual(tuple(row),(21600,900))

    def test_stock_policy_edit_keeps_quote_and_recalculates_cost(self):
        set_bulk_quote(self.db,1,48,19200)
        update_policy(self.db,[1],5,24,'stocked','Bin 5')
        self.assertEqual(self.db.execute('SELECT cost FROM products WHERE id=1').fetchone()[0],800)
        self.assertEqual(cost_history(self.db,1)[0]['change_type'],'bulk_quote')
        with self.assertRaises(ValueError):update_policy(self.db,[1],5,0,'stocked')
        self.assertEqual(self.db.execute('SELECT reorder_qty FROM products WHERE id=1').fetchone()[0],24)

    def test_manual_override_keeps_history_and_clears_quote(self):
        set_bulk_quote(self.db,1,48,19200)
        edit_product_field(self.db,1,'cost','$5.25','staff')
        row=self.db.execute('SELECT cost,reorder_cost_total,inventory_unit_cost FROM products WHERE id=1').fetchone()
        self.assertEqual(tuple(row),(525,None,450))
        changes=cost_history(self.db,1)
        self.assertEqual((changes[0]['prior_cost'],changes[0]['new_cost'],changes[0]['change_type']),
                         (400,525,'manual_override'))

    def test_price_tiers_and_rounded_draft(self):
        update_policy(self.db,[1],5,20)
        set_bulk_quote(self.db,1,48,19200,case_pack_qty=12,min_order_qty=24)
        set_price_tier(self.db,1,24,390)
        set_price_tier(self.db,1,48,350)
        self.assertEqual(quote_for_qty(self.db,1,23)[0],400)
        self.assertEqual(quote_for_qty(self.db,1,24)[0],390)
        self.assertEqual(quote_for_qty(self.db,1,48)[0],350)
        self.assertEqual(suggested_order_qty(5,12,24),24)
        rec=reorder_recommendations(self.db)[0]
        self.assertEqual((rec['suggested_qty'],rec['unit_cost']),(60,350))
        ids,_=create_reorder_drafts(self.db)
        line=self.db.execute('SELECT qty,unit_cost FROM po_items WHERE po_id=?',(ids[0],)).fetchone()
        self.assertEqual(tuple(line),(60,350))
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(ids[0],)).fetchone()[0],60*350)
        self.assertTrue(delete_price_tier(self.db,1,24))
        self.assertEqual(quote_for_qty(self.db,1,24)[0],400)

    def test_supplier_reassignment_does_not_reuse_old_tiers(self):
        set_price_tier(self.db,1,24,390)
        with self.db:
            self.db.execute("INSERT INTO suppliers(id,name) VALUES(2,'Alternate Vendor')")
            self.db.execute('UPDATE products SET supplier_id=2 WHERE id=1')
        self.assertEqual(quote_for_qty(self.db,1,24)[0],450)
        set_price_tier(self.db,1,24,315)
        self.assertEqual(quote_for_qty(self.db,1,24)[0],315)
        with self.db:self.db.execute('UPDATE products SET supplier_id=1 WHERE id=1')
        self.assertEqual(quote_for_qty(self.db,1,24)[0],390)

    def test_received_items_update_actual_basis_not_quote(self):
        set_bulk_quote(self.db,1,48,19200)
        with self.db:
            poid=self.db.execute("INSERT INTO purchase_orders(supplier_id,ordered_on,status,total) VALUES(1,'2026-11-14','Open',3000)").lastrowid
            lineid=self.db.execute('INSERT INTO po_items(po_id,product_id,qty,unit_cost) VALUES(?,?,?,?)',(poid,1,5,600)).lastrowid
        receipt,status=receive_po(self.db,poid,{lineid:5})
        row=self.db.execute('SELECT qty,cost,inventory_unit_cost FROM products WHERE id=1').fetchone()
        self.assertEqual(tuple(row),(8,400,544)) # (3*450 + 5*600)/8 = 543.75 => 544
        self.assertEqual(inventory_summary(self.db)['stock_value'],8*544)
        prior=self.db.execute('SELECT COUNT(*) FROM journal WHERE source_type=?',('po_receipt',)).fetchone()[0]
        set_bulk_quote(self.db,1,48,24000)
        self.assertEqual(self.db.execute('SELECT inventory_unit_cost FROM products WHERE id=1').fetchone()[0],544)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM journal WHERE source_type=?',('po_receipt',)).fetchone()[0],prior)

    def test_invalid_values_rollback(self):
        for args in ((0,1000),(48,-1),(48,1200)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):set_bulk_quote(self.db,1,*args,case_pack_qty=0 if args==(48,1200) else 1)
        self.assertIsNone(self.db.execute('SELECT reorder_cost_total FROM products WHERE id=1').fetchone()[0])
        with self.assertRaises(ValueError):set_price_tier(self.db,1,0,500)
        with self.assertRaises(ValueError):update_pack_rules(self.db,1,0,1)
        self.assertFalse(cost_history(self.db,1))

if __name__=='__main__':unittest.main()
