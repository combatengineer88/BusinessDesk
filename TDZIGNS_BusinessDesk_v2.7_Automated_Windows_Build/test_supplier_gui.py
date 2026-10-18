"""Optional Tkinter GUI test. Run on a Windows desktop or via xvfb-run on Linux."""
import os
import tempfile
from tkinter import ttk
import tkinter as tk

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='businessdesk_supplier_gui_')
from core_v1 import connect
from businessdesk import BusinessDesk, schema
from supplier_catalog import create_supplier_po


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def button(dialog,text):
    return next(w for w in walk(dialog) if isinstance(w,ttk.Button) and w.cget('text')==text)

root=tk.Tk();root.withdraw()
db=connect();schema(db)
with db:
    db.execute("INSERT INTO suppliers(name) VALUES('Alpha Supply')")
    db.execute("INSERT INTO suppliers(name) VALUES('Beta Wholesale')")
app=BusinessDesk.__new__(BusinessDesk)
app.root=root;app.db=db;app.user={'role':'admin','username':'tester'}
app.safe=lambda callback:callback()
original=tk.Toplevel.wait_window

def automated(dialog,window=None):
    title=dialog.title()
    if title=='Add product':
        entries=sorted((w for w in dialog.winfo_children() if type(w) is ttk.Entry),key=lambda w:w.grid_info()['row'])
        for widget,text in zip(entries,['PR1','BAR123','Test Product','Description','19.99','8.50','5']):
            widget.delete(0,'end');widget.insert(0,text)
        supplier=next(w for w in dialog.winfo_children() if isinstance(w,ttk.Combobox))
        assert supplier['values'][1].startswith('Alpha Supply')
        supplier.current(1)
        button(dialog,'Save product').invoke()
    elif 'Select Supplier' in title:
        supplier=next(w for w in walk(dialog) if isinstance(w,ttk.Combobox))
        supplier.current(0)
        button(dialog,'Continue').invoke()
    elif 'New Purchase Order' in title and 'Select Supplier' not in title:
        select=next(w for w in walk(dialog) if isinstance(w,ttk.Combobox))
        values=list(select['values'])
        assert len(values)==1 and values[0].startswith('PR1')
        select.current(0)
        select.event_generate('<<ComboboxSelected>>')
        qty=next(w for w in walk(dialog) if type(w) is ttk.Entry)
        qty.delete(0,'end');qty.insert(0,'4')
        button(dialog,'Add to PO').invoke()
        button(dialog,'Create purchase order').invoke()
    else:raise RuntimeError('Unexpected dialog: '+title)

tk.Toplevel.wait_window=automated
try:
    tab=ttk.Frame(root);tab.pack()
    app.products(tab)
    button(tab,'Add product').invoke()
    product=db.execute('SELECT * FROM products WHERE sku=?',('PR1',)).fetchone()
    assert product is not None and product['supplier_id']==1
    supplier=app.select_po_supplier()
    assert supplier['supplier_id']==1
    items=app.select_po_products(1)
    assert items==[(product['id'],4,850)],items
    po_id=create_supplier_po(db,1,'',items,'2026-10-17')
    assert db.execute('SELECT total FROM purchase_orders WHERE id=?',(po_id,)).fetchone()[0]==3400
    print('PASS: supplier product editor, PO supplier dropdown, supplier product dropdown, PO save')
finally:
    tk.Toplevel.wait_window=original
    db.close();root.destroy()
