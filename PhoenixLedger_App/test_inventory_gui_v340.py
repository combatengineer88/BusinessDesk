"""Manual/headless xvfb GUI exercise (not run on CI agents without a desktop)."""
import os
import tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import patch

os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='phoenix_340_gui_')
from core_v1 import connect
from businessdesk import PhoenixLedger,schema
from modern_theme import apply
from inventory_management import movements
from inventory_dialogs import scan_to_adjust,review_reorders,configure_inventory_policy,show_history

def all_children(widget):
    for w in widget.winfo_children():
        yield w
        yield from all_children(w)

def button(widget,name):
    return next((w for w in all_children(widget) if isinstance(w,ttk.Button) and w.cget('text')==name),None)

root=tk.Tk();root.geometry('1180x720');apply(root)
db=connect();schema(db)
with db:
    db.execute("INSERT INTO suppliers(name) VALUES('Test Supplier')")
    db.execute("INSERT INTO products(sku,name,barcode,qty,cost,price,supplier_id) VALUES('M100','Blue Mug','12345',3,250,1200,1)")
    db.execute("INSERT INTO products(sku,name,barcode,qty,cost,price,supplier_id) VALUES('S100','Shirt','67890',0,700,2000,1)")
app=PhoenixLedger.__new__(PhoenixLedger)
app.db=db;app.root=root;app.user={'id':1,'username':'tester','role':'admin'}
app._home_actions={};app.safe=lambda action:action()
p=ttk.Frame(root);p.pack(fill='both',expand=True)
app.products(p);root.update()
for required in ('Scan to Adjust','Movement History','Stock & Reorder Rules','Suggested Reorders'):
    assert button(p,required), f'Missing button {required}'
tree=next(w for w in all_children(p) if isinstance(w,ttk.Treeview))
assert len(tree.get_children())==2
assert 'Reorder at' in tree['columns']
assert tree.winfo_height()>80
root.geometry('880x560');root.update()
assert tree.winfo_height()>45, tree.winfo_height()

# Scanner accepts keyboard-enter input and saves transaction history.
import inventory_dialogs
inventory_dialogs.messagebox.showerror=lambda *args,**kwargs:print('ERROR POPUP',args,kwargs,flush=True)
dlg=scan_to_adjust(root,db,actor='tester');root.update()
entries=[w for w in all_children(dlg) if isinstance(w,ttk.Entry)]
entries[0].insert(0,'12345');button(dlg,'Find Product').invoke();root.update()
entries[2].delete(0,'end');entries[2].insert(0,'5')
print('SCAN entries', [e.get() for e in entries],flush=True)
button(dlg,'Save Adjustment').invoke();root.update()
print('SAVE attempted',flush=True)
assert db.execute('SELECT qty FROM products WHERE sku="M100"').fetchone()[0]==8
assert movements(db,1)[0]['actor']=='tester'
dlg.destroy();root.update()

# Policy dialog adjusts order points and preserves inventory.
win=configure_inventory_policy(root,db,[1]);root.update()
assert button(win,'Save Policy')
button(win,'Save Policy').invoke();root.update()
assert db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0]==8

win=review_reorders(root,db);root.update()
assert button(win,'Create Draft POs')
with patch('inventory_dialogs.messagebox.askyesno',return_value=True),\
     patch('inventory_dialogs.messagebox.showinfo',return_value=None):
    button(win,'Create Draft POs').invoke();root.update()
assert db.execute("SELECT count(*) FROM purchase_orders WHERE status='Draft'").fetchone()[0] == 1
win.destroy();root.update()

win=show_history(root,db);root.update()
assert button(win,'Export History CSV')
win.destroy();root.update()
print('PASS: v3.4 graphical inventory, scan-to-adjust, policy, reorder draft, history, narrow layout')
db.close();root.destroy()
