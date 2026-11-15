"""Manual xvfb GUI smoke test for the PhoenixLedger v3.5 product costing tab."""
import os,tempfile,tkinter as tk
from tkinter import ttk
from unittest.mock import patch
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='phoenix_350_gui_')
from core_v1 import connect
from businessdesk import PhoenixLedger,schema
from modern_theme import apply
from costing_dialogs import open_bulk_pricing_dialog

def descendants(widget):
    for w in widget.winfo_children():
        yield w
        yield from descendants(w)

def button(root,name):
    return next(w for w in descendants(root) if isinstance(w,ttk.Button) and w.cget('text')==name)
root=tk.Tk();root.geometry('1190x740');apply(root)
db=connect();schema(db)
with db:
    db.execute("INSERT INTO suppliers(name) VALUES('Bulk Vendor')")
    db.execute("INSERT INTO products(sku,name,barcode,qty,cost,price,supplier_id) VALUES('TS-001','Test Shirt','001234',3,450,1299,1)")
app=PhoenixLedger.__new__(PhoenixLedger)
app.db=db;app.root=root;app.user={'id':1,'username':'tester','role':'admin'}
app._home_actions={};app.safe=lambda call:call()
p=ttk.Frame(root);p.pack(fill='both',expand=True);app.products(p);root.update()
tree=next(w for w in descendants(p) if isinstance(w,ttk.Treeview))
assert 'Reorder Cost' in tree['columns']
assert 'Margin %' in tree['columns']
assert button(p,'Bulk Cost & Pricing')
tree.selection_set(tree.get_children()[0]);root.update()
with patch('costing_dialogs.messagebox.showinfo',return_value=None):
    button(p,'Bulk Cost & Pricing').invoke()
    root.update()
    dlg=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
    assert button(dlg,'Save Bulk Quote & Pack Rules')
    entries=[w for w in descendants(dlg) if isinstance(w,ttk.Entry)]
    assert len(entries)>=6
    entries[0].delete(0,'end');entries[0].insert(0,'48')
    entries[1].insert(0,'192')
    entries[2].delete(0,'end');entries[2].insert(0,'12')
    entries[3].delete(0,'end');entries[3].insert(0,'24')
    root.update()
    button(dlg,'Save Bulk Quote & Pack Rules').invoke();root.update()
    row=db.execute('SELECT reorder_cost_total,cost,inventory_unit_cost FROM products WHERE id=1').fetchone()
    assert tuple(row)==(19200,400,450),row
    # Different window sizes should keep the Save button within the dialog.
    dlg.geometry('620x430');root.update()
    save=button(dlg,'Save Bulk Quote & Pack Rules')
    assert save.winfo_rooty()>=dlg.winfo_rooty()
    assert save.winfo_rooty()+save.winfo_height()<=dlg.winfo_rooty()+dlg.winfo_height()+10
    button(dlg,'Close').invoke()
root.update();db.close();root.destroy()
print('PASS: v3.5 Products reorder cost column, pricing GUI, save and smaller window')
