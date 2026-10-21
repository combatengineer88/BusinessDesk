"""Atomic conversion and payment operations shared by the UI and tests."""
from datetime import date

def convert_estimate(db, document_id, charge_credit=False):
    with db:
        doc=db.execute('SELECT kind FROM documents WHERE id=?',(document_id,)).fetchone()
        if doc is None: raise ValueError('Document not found.')
        if doc['kind']!='Estimate': raise ValueError('Select an estimate to convert.')
        lines=db.execute('SELECT product_id,qty FROM document_items WHERE document_id=?',(document_id,)).fetchall()
        required={}
        for line in lines:
            if line['product_id'] is not None:
                pid=line['product_id'];required[pid]=required.get(pid,0)+line['qty']
        for pid,qty in required.items():
            product=db.execute('SELECT qty FROM products WHERE id=?',(pid,)).fetchone()
            if product is None or product['qty']<qty:
                raise ValueError(f'Not enough stock for product #{pid}. Need {qty}, available {product["qty"] if product else 0}.')
        if charge_credit:
            from account_workflows import validate_credit_charge
            doc_amount=db.execute('SELECT customer_id,total FROM documents WHERE id=?',(document_id,)).fetchone()
            validate_credit_charge(db,doc_amount['customer_id'],doc_amount['total'])
        # v2 journal triggers post revenue when kind changes only if an explicit journal is created below.
        from account_workflows import credit_due_date
        due=credit_due_date(db,doc_amount['customer_id']) if charge_credit else ''
        db.execute("UPDATE documents SET kind='Invoice',status='Open',credit_account=?,credit_due_on=? WHERE id=?",
                   (int(bool(charge_credit)),due,document_id))
        for pid,qty in required.items():
            db.execute('UPDATE products SET qty=qty-? WHERE id=?',(qty,pid))
        # Preserve original invoice/estimate date; conversion posts journal with that date.
        doc=db.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
        journal=db.execute('INSERT INTO journal(posted_on,memo,source_type,source_id) VALUES(?,?,?,?)',
                           (date.today().isoformat(),f'Invoice #{document_id} converted from estimate','invoice',document_id)).lastrowid
        db.execute('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(journal,'Accounts Receivable',doc['total'],0))
        db.execute('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(journal,'Sales Revenue',0,doc['subtotal']))
        if doc['tax']:
            db.execute('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(journal,'Sales Tax Payable',0,doc['tax']))
        for item in db.execute('SELECT id,product_id,qty FROM document_items WHERE document_id=?',(document_id,)).fetchall():
            if item['product_id'] is None: continue
            cost=db.execute('SELECT cost FROM products WHERE id=?',(item['product_id'],)).fetchone()['cost']*item['qty']
            j=db.execute('INSERT INTO journal(posted_on,memo,source_type,source_id) VALUES(?,?,?,?)',
                         (date.today().isoformat(),f'Cost of goods for invoice item #{item["id"]}','cogs',item['id'])).lastrowid
            db.execute('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(j,'Cost of Goods Sold',cost,0))
            db.execute('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',(j,'Inventory',0,cost))
    return document_id

def record_invoice_payment(db,document_id,amount,method):
    with db:
        doc=db.execute('SELECT kind,total FROM documents WHERE id=?',(document_id,)).fetchone()
        if doc is None: raise ValueError('Document not found.')
        if doc['kind']!='Invoice': raise ValueError('This is an estimate. Select Convert estimate to invoice first.')
        paid=db.execute('SELECT coalesce(sum(amount),0) FROM payments WHERE document_id=?',(document_id,)).fetchone()[0]
        due=doc['total']-paid
        if amount<=0 or amount>due: raise ValueError(f'Payment must be greater than zero and no more than the remaining balance ({due/100:.2f}).')
        db.execute('INSERT INTO payments(document_id,paid_on,amount,method) VALUES(?,?,?,?)',
                   (document_id,date.today().isoformat(),amount,method))
        db.execute('UPDATE documents SET status=? WHERE id=?',('Paid' if amount==due else 'Partially Paid',document_id))
    return due-amount
