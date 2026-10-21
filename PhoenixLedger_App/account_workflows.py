"""PhoenixLedger purchasing and customer-credit ledger operations.

All amounts are integer cents. Database writes are atomic and journal transactions
balance. Existing fully-received purchase orders are recognized without
creating duplicate inventory or payable entries.
"""
from datetime import date, datetime, timedelta


def _date(value):
    value = value or date.today().isoformat()
    datetime.strptime(value, '%Y-%m-%d')
    return value


def _amount(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Enter a positive amount in whole cents.')
    return value


def ensure_schema(db):
    """Idempotent migration. Caller has already initialized the v1/v2 schema."""
    with db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(po_items)')}
        if 'received_qty' not in columns:
            db.execute('ALTER TABLE po_items ADD COLUMN received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty>=0)')
            # Legacy full receipts already incremented inventory and posted AP.
            db.execute("""UPDATE po_items SET received_qty=qty
                          WHERE po_id IN (SELECT id FROM purchase_orders WHERE status='Received')""")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS po_receipts(
            id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            received_on TEXT NOT NULL, total INTEGER NOT NULL CHECK(total>=0), notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS po_receipt_lines(
            id INTEGER PRIMARY KEY, receipt_id INTEGER NOT NULL REFERENCES po_receipts(id),
            po_item_id INTEGER NOT NULL REFERENCES po_items(id),
            qty INTEGER NOT NULL CHECK(qty>0), unit_cost INTEGER NOT NULL CHECK(unit_cost>=0));
        CREATE TABLE IF NOT EXISTS supplier_payments(
            id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            paid_on TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
            method TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS customer_credit_accounts(
            customer_id INTEGER PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            credit_limit INTEGER NOT NULL DEFAULT 0 CHECK(credit_limit>=0),
            terms_days INTEGER NOT NULL DEFAULT 30 CHECK(terms_days BETWEEN 0 AND 365));
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(documents)')}
        if 'credit_account' not in columns:
            db.execute('ALTER TABLE documents ADD COLUMN credit_account INTEGER NOT NULL DEFAULT 0 CHECK(credit_account IN (0,1))')
        if 'credit_due_on' not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN credit_due_on TEXT NOT NULL DEFAULT ''")
        db.execute('CREATE INDEX IF NOT EXISTS idx_po_receipts_order ON po_receipts(po_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_supplier_payments_order ON supplier_payments(po_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_documents_credit ON documents(customer_id,kind,credit_account)')


def _post(db, when, memo, source_type, source_id, entries):
    debit=sum(item[1] for item in entries)
    credit=sum(item[2] for item in entries)
    if debit != credit or debit <= 0:
        raise ValueError('Unbalanced or empty journal posting.')
    row=db.execute('INSERT INTO journal(posted_on,memo,source_type,source_id) VALUES(?,?,?,?)',
                   (when,memo,source_type,source_id))
    db.executemany('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',
                   [(row.lastrowid, name, dr, cr) for name,dr,cr in entries])


def po_lines(db, po_id):
    return list(db.execute('''SELECT l.id,l.product_id,p.name,l.qty,l.received_qty,l.unit_cost
                              FROM po_items l JOIN products p ON p.id=l.product_id
                              WHERE l.po_id=? ORDER BY l.id''',(po_id,)))


def receive_po(db, po_id, quantities, received_on=None, notes=''):
    """Receive some/all remaining quantities by po_item ID, return (receipt_id,status).

    Quantities can be a dict {po_item_id: quantity}. Already-received quantities
    cannot be received again. Zero on other lines is permitted.
    """
    when=_date(received_on)
    if not isinstance(quantities,dict):
        raise ValueError('Receipt requires a map of PO line IDs to quantities.')
    with db:
        po=db.execute('SELECT status FROM purchase_orders WHERE id=?',(po_id,)).fetchone()
        if po is None:raise ValueError('Purchase order not found.')
        if po['status'] not in ('Open','Partially Received'):
            raise ValueError('This purchase order is already fully received.')
        lines=po_lines(db,po_id)
        known={line['id']:line for line in lines}
        if not lines:raise ValueError('This PO has no order lines.')
        received=[]
        for line_id, qty in quantities.items():
            if type(line_id) is not int or line_id not in known:
                raise ValueError('A receipt line does not belong to this purchase order.')
            if type(qty) is not int or qty < 0:
                raise ValueError('Receipt quantities must be nonnegative whole numbers.')
            line=known[line_id]
            if qty > line['qty']-line['received_qty']:
                raise ValueError(f'Receipt exceeds remaining quantity for {line["name"]}.')
            if qty:received.append((line,qty))
        if not received:raise ValueError('Receive at least one item.')
        total=sum(qty * line['unit_cost'] for line,qty in received)
        receipt_id=db.execute('INSERT INTO po_receipts(po_id,received_on,total,notes) VALUES(?,?,?,?)',
                              (po_id,when,total,str(notes or ''))).lastrowid
        for line,qty in received:
            db.execute('INSERT INTO po_receipt_lines(receipt_id,po_item_id,qty,unit_cost) VALUES(?,?,?,?)',
                       (receipt_id,line['id'],qty,line['unit_cost']))
            db.execute('UPDATE po_items SET received_qty=received_qty+? WHERE id=?',(qty,line['id']))
            db.execute('UPDATE products SET qty=qty+? WHERE id=?',(qty,line['product_id']))
        outstanding=db.execute('SELECT count(*) FROM po_items WHERE po_id=? AND received_qty<qty',(po_id,)).fetchone()[0]
        status='Partially Received' if outstanding else 'Received'
        db.execute('UPDATE purchase_orders SET status=? WHERE id=?',(status,po_id))
        if total:
            _post(db,when,f'Purchase order #{po_id}, receipt #{receipt_id}','po_receipt',receipt_id,
                  [('Inventory',total,0),('Accounts Payable',0,total)])
    return receipt_id,status


def po_received_value(db,po_id):
    """Include journal-backed legacy full PO receipt and all new receipts."""
    new=db.execute('SELECT coalesce(sum(total),0) FROM po_receipts WHERE po_id=?',(po_id,)).fetchone()[0]
    # Prior releases posted a single `po` journal on full receiving.
    old=db.execute('''SELECT coalesce(sum(l.credit)-sum(l.debit),0)
                      FROM journal j JOIN journal_lines l ON l.journal_id=j.id
                      WHERE j.source_type='po' AND j.source_id=? AND l.account='Accounts Payable' ''',
                   (po_id,)).fetchone()[0]
    return new+old


def po_payments_total(db,po_id):
    return db.execute('SELECT coalesce(sum(amount),0) FROM supplier_payments WHERE po_id=?',(po_id,)).fetchone()[0]


def po_balance(db,po_id):
    if not db.execute('SELECT 1 FROM purchase_orders WHERE id=?',(po_id,)).fetchone():
        raise ValueError('Purchase order not found.')
    return po_received_value(db,po_id)-po_payments_total(db,po_id)


def record_supplier_payment(db,po_id,amount,method='',reference='',paid_on=None):
    amount=_amount(amount)
    when=_date(paid_on)
    with db:
        if amount > po_balance(db,po_id):
            raise ValueError('Payment exceeds received but unpaid supplier balance.')
        ident=db.execute('''INSERT INTO supplier_payments(po_id,paid_on,amount,method,reference)
                             VALUES(?,?,?,?,?)''',(po_id,when,amount,str(method or ''),str(reference or ''))).lastrowid
        _post(db,when,f'Supplier payment PO #{po_id}','supplier_payment',ident,
              [('Accounts Payable',amount,0),('Cash',0,amount)])
    return ident


def credit_info(db,customer_id):
    if not db.execute('SELECT 1 FROM customers WHERE id=?',(customer_id,)).fetchone():
        raise ValueError('Customer not found.')
    row=db.execute('SELECT enabled,credit_limit,terms_days FROM customer_credit_accounts WHERE customer_id=?',
                   (customer_id,)).fetchone()
    enabled=bool(row['enabled']) if row else False
    limit=row['credit_limit'] if row else 0
    terms=row['terms_days'] if row else 30
    used=db.execute('''SELECT coalesce(sum(d.total-coalesce(
                        (SELECT sum(p.amount) FROM payments p WHERE p.document_id=d.id),0)),0)
                       FROM documents d WHERE d.customer_id=? AND d.kind='Invoice' AND d.credit_account=1''',
                    (customer_id,)).fetchone()[0]
    return {'enabled':enabled,'limit':limit,'terms_days':terms,'used':used,'available':max(0,limit-used)}


def configure_credit(db,customer_id,enabled,limit,terms_days=30):
    if type(enabled) is not bool or type(limit) is not int or limit<0:
        raise ValueError('Credit status and limit are invalid.')
    if type(terms_days) is not int or not 0<=terms_days<=365:
        raise ValueError('Credit terms must be between 0 and 365 days.')
    with db:
        info=credit_info(db,customer_id)
        if not enabled and info['used']>0:
            raise ValueError('Credit account has an unpaid balance. Pay off account invoices before disabling.')
        if enabled and limit<info['used']:
            raise ValueError('Credit limit cannot be less than the current balance.')
        db.execute('''INSERT INTO customer_credit_accounts(customer_id,enabled,credit_limit,terms_days)
                      VALUES(?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET
                      enabled=excluded.enabled,credit_limit=excluded.credit_limit,terms_days=excluded.terms_days''',
                   (customer_id,int(enabled),limit,terms_days))
    return credit_info(db,customer_id)


def credit_due_date(db,customer_id,invoice_date=None):
    account=credit_info(db,customer_id)
    return (date.fromisoformat(_date(invoice_date))+timedelta(days=account['terms_days'])).isoformat()


def validate_credit_charge(db,customer_id,total):
    if type(total) is not int or total<0:raise ValueError('Credit charge must be a nonnegative integer amount.')
    account=credit_info(db,customer_id)
    if not account['enabled']:
        raise ValueError('Customer credit account must be enabled before charging invoices to it.')
    if total>account['available']:
        raise ValueError(f'Insufficient customer credit. Available: ${account["available"]/100:.2f}.')
    return account


def charge_existing_invoice(db,document_id):
    """Mark an existing unpaid invoice on-account without re-posting revenue/A/R."""
    with db:
        row=db.execute('SELECT kind,customer_id,total,credit_account FROM documents WHERE id=?',
                       (document_id,)).fetchone()
        if row is None or row['kind']!='Invoice':raise ValueError('Select an invoice.')
        if row['credit_account']:raise ValueError('Invoice is already on the credit account.')
        paid=db.execute('SELECT coalesce(sum(amount),0) FROM payments WHERE document_id=?',
                        (document_id,)).fetchone()[0]
        balance=row['total']-paid
        if balance<=0:raise ValueError('Invoice is already paid.')
        validate_credit_charge(db,row['customer_id'],balance)
        db.execute('UPDATE documents SET credit_account=1,credit_due_on=? WHERE id=?',
                   (credit_due_date(db,row['customer_id']),document_id))
    return balance


def apply_credit_payment(db,customer_id,amount,method='',paid_on=None):
    """Apply one customer account payment oldest-invoice-first, atomically.

    Uses the existing payments table and triggers, thus reduces Accounts
    Receivable exactly once and never posts duplicate accounting entries.
    """
    amount=_amount(amount)
    when=_date(paid_on)
    with db:
        credit_info(db,customer_id)
        rows=list(db.execute('''SELECT d.id,d.total-coalesce((SELECT sum(p.amount) FROM payments p
                           WHERE p.document_id=d.id),0) AS due FROM documents d
                           WHERE d.customer_id=? AND d.kind='Invoice' AND d.credit_account=1
                           ORDER BY d.created,d.id''',(customer_id,)))
        due=sum(max(0,r['due']) for r in rows)
        if amount>due:raise ValueError('Payment exceeds customer credit balance.')
        allocations=[]
        remaining=amount
        for row in rows:
            applied=min(remaining,max(0,row['due']))
            if not applied:continue
            db.execute('INSERT INTO payments(document_id,paid_on,amount,method) VALUES(?,?,?,?)',
                       (row['id'],when,applied,str(method or 'Customer account payment')))
            db.execute('UPDATE documents SET status=? WHERE id=?',
                       ('Paid' if applied==row['due'] else 'Partially Paid',row['id']))
            allocations.append((row['id'],applied))
            remaining-=applied
            if not remaining:break
        assert remaining==0
    return allocations
