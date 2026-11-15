"""PhoenixLedger 3.5: bulk reorder quotes, pack rules, supplier tiers and cost history.

Money is stored as integer cents. `products.cost` is the current *quoted* item
cost and drives PO price suggestions. `inventory_unit_cost` is a separate,
weighted-average basis used for inventory valuation and new cost-of-goods
postings. Existing journal entries are never rewritten by a supplier quote.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP


def _integer(value, name, min_value=0):
    if type(value) is not int or value < min_value or value > 10**10:
        raise ValueError(f'{name} must be a whole number of at least {min_value}.')
    return value


def rounded_cents(total, quantity):
    _integer(total,'Bulk reorder cost');_integer(quantity,'Reorder quantity',1)
    return int((Decimal(total)/Decimal(quantity)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def ensure_schema(db):
    """Idempotent schema update. Existing cost/qty/PO journal entries are unchanged."""
    columns={r[1] for r in db.execute('PRAGMA table_info(products)')}
    with db:
        fields={
            'reorder_cost_total':'INTEGER DEFAULT NULL CHECK(reorder_cost_total>=0)',
            'case_pack_qty':'INTEGER NOT NULL DEFAULT 1 CHECK(case_pack_qty>=1)',
            'min_order_qty':'INTEGER NOT NULL DEFAULT 1 CHECK(min_order_qty>=1)',
            'inventory_unit_cost':'INTEGER DEFAULT NULL CHECK(inventory_unit_cost>=0)'
        }
        for key,definition in fields.items():
            if key not in columns:
                db.execute(f'ALTER TABLE products ADD COLUMN {key} {definition}')
        # Only pre-upgrade records need their existing inventory cost seeded.
        if 'inventory_unit_cost' not in columns:
            db.execute('UPDATE products SET inventory_unit_cost=cost WHERE inventory_unit_cost IS NULL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS supplier_price_tiers (
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
            min_qty INTEGER NOT NULL CHECK(min_qty>=1),
            unit_cost INTEGER NOT NULL CHECK(unit_cost>=0),
            PRIMARY KEY(product_id,supplier_id,min_qty));
        CREATE TABLE IF NOT EXISTS product_cost_history (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now')),
            prior_cost INTEGER NOT NULL,
            new_cost INTEGER NOT NULL,
            prior_bulk_total INTEGER,
            new_bulk_total INTEGER,
            reorder_qty INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_product_cost_history
            ON product_cost_history(product_id,id DESC);
        ''')
        # A newly added product has an initial actual valuation basis independent
        # of future supplier quote changes, even when created through Excel import.
        db.executescript("""
        CREATE TRIGGER IF NOT EXISTS trg_product_initial_cost AFTER INSERT ON products
        WHEN NEW.inventory_unit_cost IS NULL
        BEGIN
          UPDATE products SET inventory_unit_cost=NEW.cost WHERE id=NEW.id;
        END;
        """)
        # The historical invoice journal entries remain untouched; this trigger
        # applies the separate inventory cost basis to NEW invoice items only.
        db.execute('DROP TRIGGER IF EXISTS trg_invoice_cost')
        db.executescript('''
        CREATE TRIGGER trg_invoice_cost AFTER INSERT ON document_items
        WHEN (SELECT kind FROM documents WHERE id=NEW.document_id)='Invoice'
        AND NEW.product_id IS NOT NULL BEGIN
          INSERT INTO journal(posted_on,memo,source_type,source_id)
          VALUES((SELECT created FROM documents WHERE id=NEW.document_id),
            'Cost of goods for invoice item #'||NEW.id,'cogs',NEW.id);
          INSERT INTO journal_lines(journal_id,account,debit,credit)
          SELECT last_insert_rowid(),'Cost of Goods Sold',NEW.qty*COALESCE(inventory_unit_cost,cost),0
          FROM products WHERE id=NEW.product_id;
          INSERT INTO journal_lines(journal_id,account,debit,credit)
          SELECT (SELECT id FROM journal WHERE source_type='cogs' AND source_id=NEW.id),
            'Inventory',0,NEW.qty*COALESCE(inventory_unit_cost,cost)
          FROM products WHERE id=NEW.product_id;
        END;
        ''')


def _product(db,product_id):
    row=db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
    if row is None:raise ValueError('Product not found.')
    return dict(row)


def _history(db,row,new_cost,new_total,new_qty,kind,actor,note):
    db.execute('''INSERT INTO product_cost_history
        (product_id,prior_cost,new_cost,prior_bulk_total,new_bulk_total,reorder_qty,change_type,actor,note)
        VALUES(?,?,?,?,?,?,?,?,?)''',(row['id'],row['cost'],new_cost,row['reorder_cost_total'],new_total,new_qty,kind,str(actor),str(note)))


def set_bulk_quote(db,product_id,reorder_qty,total_cents,case_pack_qty=None,min_order_qty=None,actor=''):
    """Store a total case/bulk cost and recompute `products.cost` per unit.

    Example: total_cents=19200, reorder_qty=48 -> cost=400 cents.
    Does not mutate prior POs, inventory valuation basis, or accounting journals.
    """
    _integer(reorder_qty,'Reorder quantity',1)
    _integer(total_cents,'Bulk reorder cost')
    cost=rounded_cents(total_cents,reorder_qty)
    with db:
        row=_product(db,product_id)
        pack=_integer(row['case_pack_qty'] if case_pack_qty is None else case_pack_qty,'Case pack',1)
        minimum=_integer(row['min_order_qty'] if min_order_qty is None else min_order_qty,'Minimum order',1)
        if (row['cost'],row['reorder_cost_total'],row['reorder_qty'],row['case_pack_qty'],row['min_order_qty']) != (cost,total_cents,reorder_qty,pack,minimum):
            _history(db,row,cost,total_cents,reorder_qty,'bulk_quote',actor,'Bulk total / reorder quantity')
            db.execute('''UPDATE products SET reorder_qty=?,reorder_cost_total=?,cost=?,
                case_pack_qty=?,min_order_qty=? WHERE id=?''',
                (reorder_qty,total_cents,cost,pack,minimum,product_id))
    return cost


def set_manual_cost(db,product_id,cost_cents,actor=''):
    """Manual item-cost override clears the bulk quote to avoid stale totals."""
    _integer(cost_cents,'Item cost')
    with db:
        row=_product(db,product_id)
        if row['cost']!=cost_cents or row['reorder_cost_total'] is not None:
            _history(db,row,cost_cents,None,row['reorder_qty'],'manual_override',actor,'Manual quoted unit cost')
            db.execute('UPDATE products SET cost=?,reorder_cost_total=NULL WHERE id=?',
                       (cost_cents,product_id))
    return cost_cents


def update_pack_rules(db,product_id,case_pack_qty,min_order_qty,actor=''):
    pack=_integer(case_pack_qty,'Case pack',1)
    minimum=_integer(min_order_qty,'Minimum order',1)
    with db:
        row=_product(db,product_id)
        if (row['case_pack_qty'],row['min_order_qty'])!=(pack,minimum):
            _history(db,row,row['cost'],row['reorder_cost_total'],row['reorder_qty'],
                     'pack_rules',actor,f'Case pack {pack}; minimum {minimum}')
            db.execute('UPDATE products SET case_pack_qty=?,min_order_qty=? WHERE id=?',(pack,minimum,product_id))


def set_price_tier(db,product_id,min_qty,unit_cost,actor=''):
    _integer(min_qty,'Tier quantity',1);_integer(unit_cost,'Tier unit cost')
    with db:
        row=_product(db,product_id)
        supplier_id=row['supplier_id']
        if supplier_id is None:raise ValueError('Assign a supplier to this product before saving quantity pricing tiers.')
        old=db.execute('SELECT unit_cost FROM supplier_price_tiers WHERE product_id=? AND supplier_id=? AND min_qty=?',
                       (product_id,supplier_id,min_qty)).fetchone()
        if old is None or int(old[0])!=unit_cost:
            db.execute('INSERT INTO supplier_price_tiers(product_id,supplier_id,min_qty,unit_cost) VALUES(?,?,?,?) '
                       'ON CONFLICT(product_id,supplier_id,min_qty) DO UPDATE SET unit_cost=excluded.unit_cost',
                       (product_id,supplier_id,min_qty,unit_cost))
            _history(db,row,row['cost'],row['reorder_cost_total'],row['reorder_qty'],
                     'tier_change',actor,f'From {min_qty} units: {unit_cost} cents/unit')


def delete_price_tier(db,product_id,min_qty,actor=''):
    with db:
        row=_product(db,product_id)
        deleted=db.execute('DELETE FROM supplier_price_tiers WHERE product_id=? AND supplier_id=? AND min_qty=?',
                           (product_id,row['supplier_id'],min_qty)).rowcount
        if deleted:_history(db,row,row['cost'],row['reorder_cost_total'],row['reorder_qty'],
                            'tier_removed',actor,f'Removed price tier from {min_qty} units')
    return bool(deleted)


def price_tiers(db,product_id):
    row=_product(db,product_id)
    if row['supplier_id'] is None:return []
    return list(db.execute('SELECT min_qty,unit_cost FROM supplier_price_tiers '
                           'WHERE product_id=? AND supplier_id=? ORDER BY min_qty',
                           (product_id,row['supplier_id'])))


def quote_for_qty(db,product_id,quantity):
    _integer(quantity,'Order quantity',1)
    row=_product(db,product_id)
    tier=db.execute('''SELECT min_qty,unit_cost FROM supplier_price_tiers
                       WHERE product_id=? AND supplier_id=? AND min_qty<=?
                       ORDER BY min_qty DESC LIMIT 1''',
                    (product_id,row['supplier_id'],quantity)).fetchone()
    if tier:
        return int(tier['unit_cost']),f'Supplier tier ≥{tier["min_qty"]}'
    return int(row['cost']),'Base quoted unit cost'


def suggested_order_qty(needed,pack=1,minimum=1):
    _integer(needed,'Suggested units');_integer(pack,'Case pack',1)
    _integer(minimum,'Minimum order',1)
    if not needed:return 0
    target=max(needed,minimum)
    return ((target+pack-1)//pack)*pack


def margin_info(price_cents,cost_cents):
    _integer(price_cents,'Selling price');_integer(cost_cents,'Unit cost')
    return {'profit_cents':price_cents-cost_cents,
            'margin_percent':(100*(price_cents-cost_cents)/price_cents if price_cents else None),
            'markup_percent':(100*(price_cents-cost_cents)/cost_cents if cost_cents else None)}


def cost_history(db,product_id,limit=200):
    _integer(limit,'History limit',1)
    return list(db.execute('''SELECT * FROM product_cost_history
         WHERE product_id=? ORDER BY id DESC LIMIT ?''',(product_id,limit)))


def update_inventory_basis_on_receipt(db,product_id,received_qty,received_unit_cost):
    """Weighted-average valuation basis on receipt; called before stock quantity update."""
    _integer(received_qty,'Received quantity',1);_integer(received_unit_cost,'Receipt unit cost')
    row=_product(db,product_id)
    old_qty=int(row['qty']);old_basis=int(row['inventory_unit_cost'] if row['inventory_unit_cost'] is not None else row['cost'])
    new_basis=rounded_cents(old_qty*old_basis + received_qty*received_unit_cost,old_qty+received_qty)
    db.execute('UPDATE products SET inventory_unit_cost=? WHERE id=?',(new_basis,product_id))
    return new_basis
