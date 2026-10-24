"""Supplier master records, forward-compatible fields, and search for PhoenixLedger.

The supplier id is stable: products, purchase orders, receipts and payment
records continue to reference the same supplier when it is edited or imported.
"""

FIELDS = ('name','contact_name','email','phone','website','address','city','state','zip_code','notes')
EXTRA_FIELDS = FIELDS[1:]
MAX_LENGTHS = {
    'name': 200, 'contact_name': 200, 'email': 254, 'phone': 80,
    'website': 300, 'address': 400, 'city': 150,
    'state': 80, 'zip_code': 32, 'notes': 2000,
}


def ensure_schema(db):
    """Add supplier detail fields without changing existing supplier IDs/data."""
    cols = {row[1] for row in db.execute('PRAGMA table_info(suppliers)')}
    if not cols:
        raise ValueError('Suppliers table is missing.')
    for key in EXTRA_FIELDS:
        if key not in cols:
            db.execute(f"ALTER TABLE suppliers ADD COLUMN {key} TEXT NOT NULL DEFAULT ''")


def normalize_supplier(values):
    record = {key: str(values.get(key) or '').strip() for key in FIELDS}
    if not record['name']:
        raise ValueError('Supplier name is required.')
    for key, limit in MAX_LENGTHS.items():
        if len(record[key]) > limit:
            raise ValueError(f'{key.replace("_", " ").title()} must be {limit} characters or fewer.')
    return record


def save_supplier(db, values, supplier_id=None):
    """Insert or update a supplier without altering its link to products/POs."""
    record = normalize_supplier(values)
    with db:
        if supplier_id is None:
            exists = db.execute('SELECT id FROM suppliers WHERE name=? COLLATE NOCASE',
                                (record['name'],)).fetchone()
            if exists:
                raise ValueError('A supplier with this name already exists. Edit it instead.')
            columns = ','.join(FIELDS)
            placeholders = ','.join('?' for _ in FIELDS)
            cur = db.execute(f'INSERT INTO suppliers({columns}) VALUES({placeholders})',
                             tuple(record[key] for key in FIELDS))
            return cur.lastrowid
        existing = db.execute('SELECT id FROM suppliers WHERE id=?',(supplier_id,)).fetchone()
        if not existing:
            raise ValueError('The supplier no longer exists.')
        duplicate = db.execute('SELECT id FROM suppliers WHERE name=? COLLATE NOCASE AND id<>?',
                               (record['name'],supplier_id)).fetchone()
        if duplicate:
            raise ValueError('Another supplier already uses that name.')
        setters = ','.join(f'{key}=?' for key in FIELDS)
        db.execute(f'UPDATE suppliers SET {setters} WHERE id=?',
                   (*[record[key] for key in FIELDS],supplier_id))
        return supplier_id


def search_suppliers(db, query=''):
    """Return supplier rows plus linked catalog/PO counts; never rename IDs."""
    pattern = '%' + str(query or '').strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
    sql = '''SELECT s.*,
        (SELECT count(*) FROM products p WHERE p.supplier_id=s.id) AS product_count,
        (SELECT count(*) FROM purchase_orders po WHERE po.supplier_id=s.id) AS po_count
        FROM suppliers s
        WHERE s.name LIKE ? ESCAPE '\\' OR s.contact_name LIKE ? ESCAPE '\\'
           OR s.email LIKE ? ESCAPE '\\' OR s.phone LIKE ? ESCAPE '\\'
           OR s.city LIKE ? ESCAPE '\\' OR s.state LIKE ? ESCAPE '\\'
        ORDER BY s.name COLLATE NOCASE,s.id'''
    return list(db.execute(sql,(pattern,)*6))
