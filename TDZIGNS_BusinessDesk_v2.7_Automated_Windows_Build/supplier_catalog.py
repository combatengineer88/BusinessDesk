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
