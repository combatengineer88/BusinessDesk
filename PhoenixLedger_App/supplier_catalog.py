"""Supplier mapping and validated purchase-order helpers. No GUI dependencies."""
from datetime import date


def supplier_choices(db):
    return list(db.execute('SELECT id,name FROM suppliers ORDER BY name COLLATE NOCASE,id'))


def lookup_supplier_id(db, name):
    """Resolve optional Excel Supplier name; reject missing or ambiguous matches."""
    name = str(name or '').strip()
    if not name:
        return None
    matches = db.execute('SELECT id FROM suppliers WHERE name=? COLLATE NOCASE', (name,)).fetchall()
    if not matches:
        raise ValueError(f"Unknown supplier '{name}'. Add or import the supplier before importing products.")
    if len(matches) != 1:
        raise ValueError(f"Supplier name '{name}' is ambiguous. Rename duplicate supplier records first.")
    return matches[0][0]


def validate_supplier_rows(db, rows):
    """Validate every product's supplied supplier name before the Excel import begins."""
    for excel_row, item in rows:
        try:
            lookup_supplier_id(db, item.get('supplier', ''))
        except ValueError as exc:
            raise ValueError(f'Excel row {excel_row}: {exc}') from exc


def products_for_supplier(db, supplier_id):
    """Only catalog products explicitly assigned to the selected supplier."""
    return list(db.execute('''SELECT id,sku,name,cost,qty FROM products
        WHERE supplier_id=? ORDER BY name COLLATE NOCASE,sku''', (supplier_id,)))


def create_supplier_po(db, supplier_id, notes, items, ordered_on=None):
    """Create a PO atomically; reject products belonging to another supplier."""
    if not items:
        raise ValueError('Purchase order requires at least one product.')
    if not db.execute('SELECT 1 FROM suppliers WHERE id=?', (supplier_id,)).fetchone():
        raise ValueError('Supplier no longer exists.')
    if not isinstance(notes, str):
        raise ValueError('PO notes must be text.')
    seen = set()
    total = 0
    for product_id, quantity, cost in items:
        if type(quantity) is not int or quantity <= 0 or type(cost) is not int or cost < 0:
            raise ValueError('PO quantities must be positive whole numbers and costs cannot be negative.')
        if product_id in seen:
            raise ValueError('The same product appears twice on this purchase order.')
        seen.add(product_id)
        if not db.execute('SELECT 1 FROM products WHERE id=? AND supplier_id=?', (product_id,supplier_id)).fetchone():
            raise ValueError(f'Product ID {product_id} is not assigned to the selected supplier.')
        total += quantity * cost
    with db:
        cursor = db.execute('INSERT INTO purchase_orders(supplier_id,ordered_on,notes,total) VALUES(?,?,?,?)',
                            (supplier_id, ordered_on or date.today().isoformat(), notes, total))
        db.executemany('INSERT INTO po_items(po_id,product_id,qty,unit_cost) VALUES(?,?,?,?)',
                       [(cursor.lastrowid, *item) for item in items])
    return cursor.lastrowid


def update_supplier_po(db, po_id, notes, items):
    """Atomically replace line items on an OPEN purchase order.

    Receiving posts inventory and an accounting journal, so received orders
    cannot be changed. Existing lines remain editable if their product has
    since been reassigned to another supplier; new lines must belong to the
    PO supplier.
    """
    if not isinstance(notes, str):
        raise ValueError('Purchase order notes must be text.')
    if not items:
        raise ValueError('A purchase order must contain at least one product.')
    with db:
        po = db.execute('SELECT supplier_id,status FROM purchase_orders WHERE id=?',
                        (po_id,)).fetchone()
        if po is None:
            raise ValueError('Purchase order no longer exists.')
        if po['status'] != 'Open':
            raise ValueError('Only open purchase orders may be edited. Received POs have already affected inventory and accounting.')
        supplier_id = po['supplier_id']
        originals = {row[0] for row in db.execute(
            'SELECT product_id FROM po_items WHERE po_id=?', (po_id,))}
        seen = set()
        total = 0
        for product_id, quantity, cost in items:
            if (type(product_id) is not int or type(quantity) is not int
                    or quantity <= 0 or type(cost) is not int or cost < 0):
                raise ValueError('Quantities must be positive whole numbers; costs must be nonnegative.')
            if product_id in seen:
                raise ValueError('A product can only appear once on a purchase order.')
            seen.add(product_id)
            product = db.execute('SELECT supplier_id FROM products WHERE id=?',
                                 (product_id,)).fetchone()
            if product is None:
                raise ValueError('A product on this purchase order no longer exists.')
            if product['supplier_id'] != supplier_id and product_id not in originals:
                raise ValueError(f'Product #{product_id} is not assigned to this supplier.')
            total += quantity * cost
        db.execute('DELETE FROM po_items WHERE po_id=?', (po_id,))
        db.executemany(
            'INSERT INTO po_items(po_id,product_id,qty,unit_cost) VALUES(?,?,?,?)',
            [(po_id, *line) for line in items])
        db.execute('UPDATE purchase_orders SET notes=?,total=? WHERE id=? AND status=\'Open\'',
                   (notes, total, po_id))
    return po_id
