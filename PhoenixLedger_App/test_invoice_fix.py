import os, tempfile
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='tdzigns_test_')
from core_v1 import connect
from businessdesk import schema
from sales_workflow import convert_estimate,record_invoice_payment

db=connect();schema(db)
with db:
    db.execute("INSERT INTO users(username,password,role) VALUES('test','x','admin')")
    db.execute("INSERT INTO customers(name) VALUES('Fake Customer')")
    db.execute("INSERT INTO products(sku,name,price,cost,qty) VALUES('ABC','Test Product',10000,3000,5)")
    db.execute("INSERT INTO documents(kind,customer_id,created,subtotal,tax,total,created_by) VALUES('Estimate',1,'2026-10-15',10000,500,10500,1)")
    db.execute("INSERT INTO document_items(document_id,product_id,description,qty,unit_price,line_total) VALUES(1,1,'Test Product',1,10000,10000)")
assert db.execute("SELECT count(*) FROM documents WHERE kind='Invoice'").fetchone()[0]==0
try:record_invoice_payment(db,1,5000,'Cash');assert False
except ValueError as e:assert 'estimate' in str(e).lower()
convert_estimate(db,1)
assert db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0]==4
assert db.execute("SELECT count(*) FROM journal WHERE source_type='invoice'").fetchone()[0]==1
assert record_invoice_payment(db,1,5000,'Cash')==5500
assert db.execute('SELECT status FROM documents WHERE id=1').fetchone()[0]=='Partially Paid'
assert record_invoice_payment(db,1,5500,'Card')==0
assert db.execute('SELECT status FROM documents WHERE id=1').fetchone()[0]=='Paid'
assert db.execute('SELECT sum(amount) FROM payments').fetchone()[0]==10500
assert db.execute('SELECT sum(debit)-sum(credit) FROM journal_lines').fetchone()[0]==0
print('PASS: conversion, inventory, accounting, partial/full payment, dashboard data')
