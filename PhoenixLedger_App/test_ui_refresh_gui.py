"""Optional developer desktop smoke test (run with Xvfb on Linux, Windows locally)."""
import os, tempfile, tkinter as tk
from tkinter import ttk
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='phoenix36_gui_')
from modern_theme import apply
from businessdesk import PhoenixLedger,schema
from core_v1 import connect

root=tk.Tk(); root.geometry('1200x740')
style=apply(root)
assert len(root._phoenix_button_art)==8
assert 'PhoenixDefault.border' in str(style.layout('TButton'))
assert 'PhoenixAccent.border' in str(style.layout('Accent.TButton'))
app=PhoenixLedger.__new__(PhoenixLedger);app.db=connect();app.root=root
app.user={'id':1,'username':'demo','role':'admin'};app._home_actions={}
app.safe=lambda fn:fn()
schema(app.db)
with app.db:
    app.db.execute("INSERT INTO suppliers(name) VALUES('Test Vendor')")
    app.db.execute("INSERT INTO customers(name) VALUES('Test Customer')")
    app.db.execute("INSERT INTO products(sku,name,qty,price,cost,supplier_id) VALUES('SHIRT','Black Shirt',10,1299,400,1)")
frame=ttk.Frame(root);frame.pack(fill='both',expand=True)
app.products(frame);root.update()

def trees(widget):
    for child in widget.winfo_children():
        if isinstance(child,ttk.Treeview):yield child
        yield from trees(child)
tree=next(trees(frame))
menu=tree._phoenix_context_menu
assert menu.index('end')>10
assert tree.get_children()
assert tree.item(tree.get_children()[0],'values')[-2:]==('No','No')
header=tree['columns']
assert 'Reorder Cost' in header and 'Image' in header
assert menu.entrycget(0,'label')=='Edit product'
root.geometry('900x580');root.update()
assert tree.winfo_height()>70
frame.destroy();root.update()

suppliers=ttk.Frame(root);suppliers.pack(fill='both',expand=True)
app.suppliers(suppliers);root.update()
st=next(trees(suppliers)); assert st._phoenix_context_menu.entrycget(0,'label')=='Edit supplier'
suppliers.destroy();root.update()

customers=ttk.Frame(root);customers.pack(fill='both',expand=True)
app.customers(customers);root.update()
ct=next(trees(customers)); assert ct._phoenix_context_menu.entrycget(0,'label')=='Edit customer'
customers.destroy();root.update()
app.db.close();root.destroy()
print('PASS: rounded styles, CSV flags, product/supplier/customer context menus, resized Products tab')
