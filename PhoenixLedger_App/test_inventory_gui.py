"""GUI smoke test, intended for an interactive Windows session or xvfb-run Linux."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk

os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='phoenix_inventory_gui_')
from core_v1 import connect
from businessdesk import PhoenixLedger, schema
from modern_theme import apply
from barcode_dialogs import open_barcode_print_dialog

root=tk.Tk();root.geometry('1160x720');root.update()
apply(root)
db=connect();schema(db)
with db:
    db.execute("INSERT INTO suppliers(name) VALUES('Sample Supplier')")
    db.execute("INSERT INTO products(id,sku,name,description,barcode,price,cost,qty,supplier_id) VALUES(1,'A100','Old Product','Widget','100200300',1550,700,18,1)")
    db.execute("INSERT INTO products(id,sku,name,description,barcode,price,cost,qty,supplier_id) VALUES(2,'B200','Second Product','Widget 2','100300400',1450,600,9,1)")
app=PhoenixLedger.__new__(PhoenixLedger)
app.root=root;app.db=db;app.user={'role':'admin','username':'tester'};app._home_actions={}
app.safe=lambda callback:callback()
tab=ttk.Frame(root);tab.pack(fill='both',expand=True)
app.products(tab)
root.update()

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

tree=next(x for x in descendants(tab) if isinstance(x,ttk.Treeview))
print('DEBUG',tree.cget('selectmode'),tree['columns'])
assert str(tree.cget('selectmode'))=='extended'
assert 'Barcode PNG' in tree['columns']
assert len(tree.get_children())==2
names={w.cget('text') for w in descendants(tab) if isinstance(w,ttk.Button)}
assert {'Print barcode stickers','Attach barcode PNG','View barcode PNG','Edit','Add product'}<=names,names
item=tree.get_children()[0]
tree.see(item);root.update()
# Double click the Name column (fourth position)
bbox=tree.bbox(item,'#4')
assert bbox,bbox
x,y,w,h=bbox
for _ in range(2):
    tree.event_generate('<ButtonPress-1>',x=x+8,y=y+h//2)
    tree.event_generate('<ButtonRelease-1>',x=x+8,y=y+h//2)
root.update()
entry=next((w for w in descendants(tree) if isinstance(w,ttk.Entry)),None)
assert entry is not None,'Inline editing textbox not created'
entry.delete(0,'end');entry.insert(0,'Updated Product')
entry.event_generate('<Return>');root.update()
assert db.execute('SELECT name FROM products WHERE id=1').fetchone()[0]=='Updated Product'

out=Path(os.environ['LOCALAPPDATA'])/'gui_stickers.pdf'
old_wait=tk.Toplevel.wait_window

def fake_wait(win,window=None):
    root.update()
    footer=next(w for w in descendants(win) if isinstance(w,ttk.Button) and w.cget('text')=='Save PDF')
    assert footer.winfo_y() >= 0
    # Confirm output action completes without a modal and dialog footer fits.
    footer.invoke()
    root.update()
    assert out.exists(),out
    win.destroy()

try:
    with patch.object(tk.Toplevel,'wait_window',fake_wait),\
         patch('barcode_dialogs.filedialog.asksaveasfilename',return_value=str(out)),\
         patch('barcode_dialogs.messagebox.showinfo',return_value=None):
         open_barcode_print_dialog(root,db,[1,2])
finally:
    tk.Toplevel.wait_window=old_wait

assert out.stat().st_size>1000
print('PASS: Products multi-select, editable cells, barcode buttons, sticker save GUI')
db.close();root.destroy()
