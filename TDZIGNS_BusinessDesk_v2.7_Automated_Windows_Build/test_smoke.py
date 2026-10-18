import os, tempfile, importlib.util
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='tdzigns_test_')
import businessdesk as b
from core_v1 import connect

db=connect();b.schema(db)
with db:
    db.execute("INSERT INTO users(username,password,role) VALUES('admin','test','admin')")
    db.execute("INSERT INTO customers(name) VALUES('Test Customer')")
    db.execute("INSERT INTO products(sku,name,price,cost,qty,barcode) VALUES('SKU1','Test Product',1200,500,10,'123456789')")
    db.execute("INSERT INTO documents(kind,customer_id,created,subtotal,tax,total,created_by) VALUES('Invoice',1,'2026-10-14',1200,60,1260,1)")
    db.execute("INSERT INTO document_items(document_id,product_id,description,qty,unit_price,line_total) VALUES(1,1,'Test Product',1,1200,1200)")
    db.execute("INSERT INTO payments(document_id,paid_on,amount) VALUES(1,'2026-10-14',1260)")
    db.execute("INSERT INTO expenses(spent_on,category,amount) VALUES('2026-10-14','Office',200)")
    db.execute("INSERT INTO suppliers(name) VALUES('Test Supplier')")
    db.execute("INSERT INTO purchase_orders(supplier_id,ordered_on,total) VALUES(1,'2026-10-14',300)")
    db.execute("INSERT INTO po_items(po_id,product_id,qty,unit_cost) VALUES(1,1,1,300)")
    b.post_journal(db,'2026-10-14','Receive PO','po',1,[('Inventory',300,0),('Accounts Payable',0,300)])
assert db.execute('SELECT sum(debit)-sum(credit) FROM journal_lines').fetchone()[0]==0
assert db.execute('SELECT count(*) FROM journal').fetchone()[0]==5
with tempfile.TemporaryDirectory() as folder:
    path=os.path.join(folder,'invoice.pdf')
    b.make_pdf(db,'Invoice',1,path)
    assert open(path,'rb').read(4)==b'%PDF'
    b.make_pdf(db,'PO',1,os.path.join(folder,'po.pdf'))
print('PASS: schema, balanced journal triggers, purchase orders, PDF exports')
