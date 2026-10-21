"""v3.1.0 receipt/payables/customer-credit regression and migration coverage."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from account_workflows import (ensure_schema,po_lines,receive_po,po_balance,
    record_supplier_payment,credit_info,configure_credit,validate_credit_charge,
    charge_existing_invoice,apply_credit_payment)
from sales_workflow import record_invoice_payment,convert_estimate
from supplier_catalog import create_supplier_po,update_supplier_po
from businessdesk import schema
import core_v1


class AccountingFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        with patch.object(core_v1,'DB',Path(self.temp.name)/'work.db'):
            self.db=core_v1.connect()
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO users(username,password,role) VALUES('admin','x','admin')")
            self.db.execute("INSERT INTO suppliers(name) VALUES('Supplier A')")
            self.db.execute("INSERT INTO customers(name) VALUES('Customer A')")
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty,supplier_id) VALUES('P-1','Part A',2000,800,10,1)")
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty,supplier_id) VALUES('P-2','Part B',1000,400,20,1)")
    def tearDown(self):
        self.db.close();self.temp.cleanup()
    def po(self):return create_supplier_po(self.db,1,'test',[(1,10,800),(2,6,400)])
    def lines(self,po_id):return {r['product_id']:r for r in po_lines(self.db,po_id)}
    def inventory(self,pid=1):return self.db.execute('SELECT qty FROM products WHERE id=?',(pid,)).fetchone()[0]
    def assert_balanced(self):
        row=self.db.execute('SELECT sum(debit),sum(credit) FROM journal_lines').fetchone()
        self.assertEqual(row[0],row[1])
    def test_partial_then_full_receipt_exact_inventory_and_ap(self):
        pid=self.po();line=self.lines(pid)
        first,status=receive_po(self.db,pid,{line[1]['id']:3,line[2]['id']:0})
        self.assertEqual(status,'Partially Received')
        self.assertEqual(self.inventory(1),13)
        self.assertEqual(self.inventory(2),20)
        self.assertEqual(po_balance(self.db,pid),2400)
        self.assertEqual(self.db.execute('SELECT total FROM po_receipts WHERE id=?',(first,)).fetchone()[0],2400)
        with self.assertRaises(ValueError):
            receive_po(self.db,pid,{line[1]['id']:8})
        self.assertEqual(self.inventory(1),13)
        with self.assertRaises(ValueError):
            update_supplier_po(self.db,pid,'change',[(1,50,800)])
        second,status=receive_po(self.db,pid,{line[1]['id']:7,line[2]['id']:6})
        self.assertEqual(status,'Received')
        self.assertEqual(self.inventory(1),20)
        self.assertEqual(self.inventory(2),26)
        self.assertEqual(po_balance(self.db,pid),10400)
        with self.assertRaises(ValueError):receive_po(self.db,pid,{line[1]['id']:1})
        self.assert_balanced()
        self.assertEqual(self.db.execute('SELECT count(*) FROM journal WHERE source_type="po_receipt"').fetchone()[0],2)

    def test_supplier_payment_partial_and_overpayment_prevention(self):
        pid=self.po();line=self.lines(pid)
        with self.assertRaises(ValueError):record_supplier_payment(self.db,pid,100)
        receive_po(self.db,pid,{line[1]['id']:2})
        self.assertEqual(po_balance(self.db,pid),1600)
        record_supplier_payment(self.db,pid,1000,'Bank transfer','REF-1')
        self.assertEqual(po_balance(self.db,pid),600)
        with self.assertRaises(ValueError):record_supplier_payment(self.db,pid,601)
        with self.assertRaises(ValueError):record_supplier_payment(self.db,pid,0)
        self.assertEqual(po_balance(self.db,pid),600)
        record_supplier_payment(self.db,pid,600)
        self.assertEqual(po_balance(self.db,pid),0)
        self.assert_balanced()
        self.assertEqual(self.db.execute('SELECT count(*) FROM supplier_payments').fetchone()[0],2)

    def test_legacy_received_migrates_without_duplicate_receiving(self):
        pid=self.po()
        # Simulate legacy full receipt before first account-workflow migration.
        with self.db:
            self.db.execute('UPDATE purchase_orders SET status="Received" WHERE id=?',(pid,))
            self.db.execute('UPDATE po_items SET received_qty=qty WHERE po_id=?',(pid,))
            journal=self.db.execute('INSERT INTO journal(posted_on,memo,source_type,source_id) VALUES(?,?,?,?)',
                                    ('2026-10-20','Legacy receipt','po',pid)).lastrowid
            self.db.executemany('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',
               [(journal,'Inventory',10400,0),(journal,'Accounts Payable',0,10400)])
        ensure_schema(self.db);ensure_schema(self.db)
        self.assertEqual(po_balance(self.db,pid),10400)
        self.assertEqual(self.db.execute('SELECT count(*) FROM po_receipts').fetchone()[0],0)
        with self.assertRaises(ValueError):receive_po(self.db,pid,{self.lines(pid)[1]['id']:1})
        record_supplier_payment(self.db,pid,10400)
        self.assertEqual(po_balance(self.db,pid),0)
        self.assert_balanced()

    def test_credit_setup_charge_existing_and_payment(self):
        cid=1
        self.assertFalse(credit_info(self.db,cid)['enabled'])
        configure_credit(self.db,cid,True,10000)
        with self.db:
            self.db.execute("INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by) VALUES('Invoice',1,'2026-10-20','Open',4400,0,4400,'',1)")
        charge_existing_invoice(self.db,1)
        self.assertEqual(credit_info(self.db,cid)['used'],4400)
        with self.assertRaises(ValueError):charge_existing_invoice(self.db,1)
        with self.assertRaises(ValueError):configure_credit(self.db,cid,True,1000)
        with self.assertRaises(ValueError):configure_credit(self.db,cid,False,10000)
        self.assertEqual(apply_credit_payment(self.db,cid,1400,'Cash'),[(1,1400)])
        self.assertEqual(credit_info(self.db,cid)['used'],3000)
        self.assertEqual(self.db.execute('SELECT status FROM documents WHERE id=1').fetchone()[0],'Partially Paid')
        with self.assertRaises(ValueError):apply_credit_payment(self.db,cid,3001)
        self.assertEqual(apply_credit_payment(self.db,cid,3000),[(1,3000)])
        self.assertEqual(credit_info(self.db,cid)['used'],0)
        self.assertEqual(self.db.execute('SELECT status FROM documents WHERE id=1').fetchone()[0],'Paid')
        configure_credit(self.db,cid,False,0)
        self.assert_balanced()

    def test_credit_payments_allocate_oldest_first_atomically(self):
        configure_credit(self.db,1,True,30000)
        with self.db:
            for month,total in [('2026-10-01',2000),('2026-10-10',4500)]:
                self.db.execute('''INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by,credit_account)
                                VALUES('Invoice',1,?,'Open',?,0,?,'',1,1)''',(month,total,total))
        self.assertEqual(apply_credit_payment(self.db,1,5000),[(1,2000),(2,3000)])
        self.assertEqual(self.db.execute('SELECT status FROM documents WHERE id=1').fetchone()[0],'Paid')
        self.assertEqual(self.db.execute('SELECT status FROM documents WHERE id=2').fetchone()[0],'Partially Paid')
        self.assertEqual(credit_info(self.db,1)['used'],1500)
        self.assertEqual(self.db.execute('SELECT count(*) FROM payments').fetchone()[0],2)
        self.assert_balanced()

    def test_convert_credit_estimate_limits_and_no_inventory_loss_on_rejection(self):
        configure_credit(self.db,1,True,3000)
        with self.db:
            self.db.execute("INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by) VALUES('Estimate',1,'2026-10-20','Open',4000,0,4000,'',1)")
            self.db.execute("INSERT INTO document_items(document_id,product_id,description,qty,unit_price,line_total) VALUES(1,1,'Test',2,2000,4000)")
        with self.assertRaises(ValueError):convert_estimate(self.db,1,charge_credit=True)
        self.assertEqual(self.inventory(),10)
        self.assertEqual(self.db.execute('SELECT kind FROM documents WHERE id=1').fetchone()[0],'Estimate')
        configure_credit(self.db,1,True,5000)
        convert_estimate(self.db,1,charge_credit=True)
        self.assertEqual(self.inventory(),8)
        self.assertEqual(self.db.execute('SELECT credit_account FROM documents WHERE id=1').fetchone()[0],1)
        self.assertEqual(credit_info(self.db,1)['used'],4000)
        self.assert_balanced()

    def test_atomic_receipt_rejects_unrelated_line(self):
        first=self.po();second=self.po()
        first_id=self.lines(first)[1]['id'];second_id=self.lines(second)[1]['id']
        with self.assertRaises(ValueError):receive_po(self.db,first,{first_id:2,second_id:2})
        self.assertEqual(self.inventory(1),10)
        self.assertEqual(self.db.execute('SELECT count(*) FROM po_receipts').fetchone()[0],0)


if __name__=='__main__':unittest.main()
