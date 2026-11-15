"""PhoenixLedger v3.4 inventory movements, scan adjustments and draft reorder planning.

This module has no GUI dependencies. All on-hand changes are audited by SQLite
triggers, including edits made outside the scan workflow and product imports.
Reorder proposals become non-receivable *Draft* POs until explicitly approved.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

STOCK_MODES = ('stocked', 'made_to_order', 'supplier_direct')


def ensure_schema(db):
    """Idempotent migration; preserve existing stock, IDs and accounting records."""
    with db:
        columns={row[1] for row in db.execute('PRAGMA table_info(products)')}
        for col, definition in {
            'reorder_point':'INTEGER NOT NULL DEFAULT 5',
            'reorder_qty':'INTEGER NOT NULL DEFAULT 20',
            'stock_mode':"TEXT NOT NULL DEFAULT 'stocked'",
            'bin_location':"TEXT NOT NULL DEFAULT ''",
        }.items():
            if col not in columns:
                db.execute(f'ALTER TABLE products ADD COLUMN {col} {definition}')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
            old_qty INTEGER NOT NULL,
            change_qty INTEGER NOT NULL,
            new_qty INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'system',
            reason TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_inv_movements_product_date
            ON inventory_movements(product_id, id DESC);
        CREATE TABLE IF NOT EXISTS inventory_change_context (
            id INTEGER PRIMARY KEY CHECK (id=1),
            source TEXT NOT NULL DEFAULT 'system',
            reason TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO inventory_change_context(id,source,reason,actor)
            VALUES(1,'system','','');
        ''')
        # A baseline makes pre-upgrade stock visible without pretending its history exists.
        db.execute('''INSERT INTO inventory_movements
            (product_id,old_qty,change_qty,new_qty,source,reason,actor)
            SELECT p.id,0,p.qty,p.qty,'baseline','Opening stock recorded during v3.4 upgrade',''
            FROM products p WHERE NOT EXISTS (
                SELECT 1 FROM inventory_movements m WHERE m.product_id=p.id)''')
        db.executescript('''
        CREATE TRIGGER IF NOT EXISTS trg_inv_product_added AFTER INSERT ON products
        BEGIN
          INSERT INTO inventory_movements(product_id,old_qty,change_qty,new_qty,source,reason,actor)
          SELECT NEW.id,0,NEW.qty,NEW.qty,
            COALESCE((SELECT source FROM inventory_change_context WHERE id=1),'system'),
            COALESCE(NULLIF((SELECT reason FROM inventory_change_context WHERE id=1),''),'New product'),
            COALESCE((SELECT actor FROM inventory_change_context WHERE id=1),'');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_inv_qty_changed AFTER UPDATE OF qty ON products
        WHEN OLD.qty != NEW.qty
        BEGIN
          INSERT INTO inventory_movements(product_id,old_qty,change_qty,new_qty,source,reason,actor)
          SELECT NEW.id,OLD.qty,NEW.qty-OLD.qty,NEW.qty,
            COALESCE((SELECT source FROM inventory_change_context WHERE id=1),'system'),
            COALESCE((SELECT reason FROM inventory_change_context WHERE id=1),''),
            COALESCE((SELECT actor FROM inventory_change_context WHERE id=1),'');
        END;
        ''')


def set_change_context(db, source='system', reason='', actor=''):
    """Caller must clear the context before committing; safe on unmigrated DBs."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_change_context'").fetchone():
        db.execute('UPDATE inventory_change_context SET source=?,reason=?,actor=? WHERE id=1',
                   (str(source),str(reason),str(actor)))


def clear_change_context(db):
    set_change_context(db)


def lookup_scan(db, code):
    """Exact, whitespace-trimmed match to SKU or barcode (USB scanners type text+Enter)."""
    code=str(code or '').strip()
    if not code:
        raise ValueError('Scan a barcode or type a SKU.')
    rows=db.execute('''SELECT * FROM products WHERE sku=? COLLATE NOCASE
                       OR barcode=? COLLATE NOCASE ORDER BY id LIMIT 3''',(code,code)).fetchall()
    if not rows:raise ValueError(f'No product matches barcode or SKU: {code}')
    if len(rows)>1:raise ValueError('Barcode/SKU matches multiple products; correct the duplicates first.')
    return dict(rows[0])


def adjust_stock(db, product_id, operation, quantity, reason, actor=''):
    """Adjust on-hand quantity atomically; audit trigger records before/after.

    operation: Add, Remove, or Set; quantity is nonnegative integer.
    A meaningful reason is mandatory, including for a physical count.
    """
    if operation not in ('Add','Remove','Set'):
        raise ValueError('Choose Add, Remove, or Set count.')
    if type(quantity) is not int or quantity < 0 or (operation!='Set' and quantity==0):
        raise ValueError('Quantity must be a positive whole number (or zero for Set count).')
    reason=str(reason or '').strip()
    if not reason:raise ValueError('Select an adjustment reason.')
    with db:
        p=db.execute('SELECT qty FROM products WHERE id=?',(product_id,)).fetchone()
        if p is None:raise ValueError('Product was not found.')
        before=int(p['qty'])
        after=before + quantity if operation=='Add' else before-quantity if operation=='Remove' else quantity
        if after<0:raise ValueError('Cannot remove more than the quantity on hand.')
        if after==before:raise ValueError('Count matches current stock; no change to save.')
        set_change_context(db,'scan_adjustment',reason,actor)
        try:
            db.execute('UPDATE products SET qty=? WHERE id=?',(after,product_id))
        finally:
            clear_change_context(db)
    return before,after


def update_policy(db, product_ids, reorder_point, reorder_qty, stock_mode='stocked', bin_location=None):
    """Update one or more products' ordering rules without affecting stock."""
    if (type(reorder_point) is not int or reorder_point<0 or
            type(reorder_qty) is not int or reorder_qty<0):
        raise ValueError('Reorder point and reorder quantity must be whole numbers >= 0.')
    if stock_mode not in STOCK_MODES:
        raise ValueError('Invalid inventory tracking mode.')
    ids=list(dict.fromkeys(product_ids))
    if not ids or any(type(i) is not int for i in ids):raise ValueError('Select products to configure.')
    with db:
        for product_id in ids:
            if db.execute('SELECT 1 FROM products WHERE id=?',(product_id,)).fetchone() is None:
                raise ValueError(f'Product #{product_id} was not found.')
            if bin_location is None:
                db.execute('UPDATE products SET reorder_point=?,reorder_qty=?,stock_mode=? WHERE id=?',
                           (reorder_point,reorder_qty,stock_mode,product_id))
            else:
                db.execute('''UPDATE products SET reorder_point=?,reorder_qty=?,stock_mode=?,bin_location=?
                              WHERE id=?''',(reorder_point,reorder_qty,stock_mode,str(bin_location).strip(),product_id))
    return len(ids)


def inventory_summary(db):
    row=db.execute('''SELECT count(*) AS count,
        sum(CASE WHEN stock_mode='stocked' AND qty=0 THEN 1 ELSE 0 END) AS out_count,
        sum(CASE WHEN stock_mode='stocked' AND qty<=reorder_point THEN 1 ELSE 0 END) AS low_count,
        coalesce(sum(CASE WHEN stock_mode='stocked' THEN qty*cost ELSE 0 END),0) AS stock_value,
        sum(CASE WHEN stock_mode<>'stocked' THEN 1 ELSE 0 END) AS nonstock_count
        FROM products''').fetchone()
    return {k:int(row[k] or 0) for k in row.keys()}


def reorder_recommendations(db):
    """Only stocked products below reorder point; subtract unreceived open/draft POs."""
    sql='''SELECT p.id,p.sku,p.name,p.supplier_id,s.name AS supplier_name,
        p.qty,p.cost,p.reorder_point,p.reorder_qty,
        COALESCE((SELECT SUM(l.qty-COALESCE(l.received_qty,0))
          FROM po_items l JOIN purchase_orders o ON o.id=l.po_id
          WHERE l.product_id=p.id AND o.status IN ('Draft','Open','Partially Received')),0) AS on_order
        FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id
        WHERE p.stock_mode='stocked' AND p.qty<=p.reorder_point AND p.reorder_qty>0
        ORDER BY s.name COLLATE NOCASE,p.name COLLATE NOCASE'''
    recommendations=[]
    for r in db.execute(sql):
        row=dict(r)
        target=int(r['reorder_point']) + int(r['reorder_qty'])
        needed=max(0,target-int(r['qty'])-int(r['on_order']))
        if needed:
            row.update({'target_qty':target,'suggested_qty':needed})
            recommendations.append(row)
    return recommendations


def create_reorder_drafts(db):
    """Create editable, non-receivable DRAFT POs grouped by assigned supplier.

    Unassigned products are returned separately and never silently ordered.
    Re-running this function will not duplicate draft quantities already on order.
    """
    with db:
        rows=reorder_recommendations(db)
        grouped=defaultdict(list)
        missing=[]
        for row in rows:
            if row['supplier_id'] is None:
                missing.append(row)
            else:
                grouped[row['supplier_id']].append(row)
        created=[]
        for supplier_id,items in sorted(grouped.items()):
            total=sum(int(r['suggested_qty'])*int(r['cost']) for r in items)
            cursor=db.execute('''INSERT INTO purchase_orders
                  (supplier_id,ordered_on,status,notes,total) VALUES(?,?,?,?,?)''',
                  (supplier_id,date.today().isoformat(),'Draft',
                   'Automatic reorder draft. Review quantities and costs, then approve before receiving.',total))
            po_id=cursor.lastrowid
            db.executemany('''INSERT INTO po_items(po_id,product_id,qty,unit_cost)
                              VALUES(?,?,?,?)''',
                           [(po_id,r['id'],r['suggested_qty'],r['cost']) for r in items])
            created.append(po_id)
    return created,missing


def approve_reorder_draft(db, po_id):
    """Explicitly mark one drafted PO as Open; no stock or accounting effects."""
    with db:
        po=db.execute('SELECT status FROM purchase_orders WHERE id=?',(po_id,)).fetchone()
        if not po:raise ValueError('Purchase order no longer exists.')
        if po['status']!='Draft':raise ValueError('Select a Draft purchase order to approve.')
        if not db.execute('SELECT 1 FROM po_items WHERE po_id=?',(po_id,)).fetchone():
            raise ValueError('Draft purchase order has no lines.')
        db.execute("UPDATE purchase_orders SET status='Open' WHERE id=?",(po_id,))
    return po_id


def movements(db, product_id=None, limit=400):
    if type(limit) is not int or not 1<=limit<=2000:
        raise ValueError('Invalid history limit.')
    sql='''SELECT m.id,m.changed_at,p.sku,p.name,m.old_qty,m.change_qty,m.new_qty,
        m.source,m.reason,m.actor FROM inventory_movements m
        JOIN products p ON p.id=m.product_id'''
    if product_id is not None:
        return list(db.execute(sql+' WHERE p.id=? ORDER BY m.id DESC LIMIT ?', (product_id,limit)))
    return list(db.execute(sql+' ORDER BY m.id DESC LIMIT ?', (limit,)))
