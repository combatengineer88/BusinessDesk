"""Accessible, resizable purchase-order editor for creating and editing open POs.

Save/Cancel stay in a dedicated bottom footer even on high-DPI Windows displays.
Changes are committed only by the explicit Save button; cancel is non-mutating.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from core_v1 import cents, money
from supplier_catalog import (supplier_choices, products_for_supplier,
                              create_supplier_po, update_supplier_po)


class PurchaseOrderEditor:
    def __init__(self, parent, db, po_id=None):
        self.parent = parent
        self.db = db
        self.po_id = po_id
        self.saved_id = None
        self.lines = {}  # product_id -> (positive integer quantity, unit_cost_cents)
        self.products = []
        self.supplier_id = None
        self.suppliers = supplier_choices(db)
        if not self.suppliers:
            raise ValueError('Add or import at least one supplier before creating a purchase order.')
        self.original_products = set()
        self.existing = None
        if po_id is not None:
            po = db.execute('SELECT * FROM purchase_orders WHERE id=?', (po_id,)).fetchone()
            if po is None:
                raise ValueError('Purchase order not found.')
            if po['status'] != 'Open':
                raise ValueError('Only Open purchase orders can be edited. Received orders already affect inventory and accounting.')
            self.existing = po
            self.supplier_id = po['supplier_id']
            for line in db.execute('SELECT product_id,qty,unit_cost FROM po_items WHERE po_id=? ORDER BY id',
                                   (po_id,)):
                self.lines[line['product_id']] = (line['qty'], line['unit_cost'])
            self.original_products = set(self.lines)

        self.window = tk.Toplevel(parent)
        self.window.title('Edit Purchase Order #' + str(po_id) if po_id else 'New Purchase Order')
        self.window.transient(parent)
        self.window.resizable(True, True)
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        width = min(990, max(640, screen_w-80))
        height = min(690, max(420, screen_h-100))
        self.window.geometry(f'{width}x{height}')
        self.window.minsize(min(700,width),min(400,height))
        self.window.protocol('WM_DELETE_WINDOW',self.cancel)
        self.window.bind('<Escape>',lambda event:self.cancel())
        self.window.bind('<Control-s>',lambda event:self.save())

        # Grid layout: only the line-item table expands/shrinks; save controls
        # remain in row 4 at the bottom regardless of DPI or window size.
        content = ttk.Frame(self.window,padding=(16,10))
        content.pack(fill='both',expand=True)
        content.columnconfigure(0,weight=1)
        content.rowconfigure(3,weight=1)

        heading = ttk.Frame(content)
        heading.grid(row=0,column=0,sticky='ew',pady=(0,10))
        ttk.Label(heading,text='Edit Purchase Order' if po_id else 'New Purchase Order',
                  style='Section.TLabel').pack(anchor='w')
        ttk.Label(heading,text='Select the supplier, add items, and save your order. Select a line to correct its quantity or cost.',
                  wraplength=900).pack(anchor='w')

        meta = ttk.Frame(content)
        meta.grid(row=1,column=0,sticky='ew',pady=(0,10))
        meta.columnconfigure(1,weight=1)
        ttk.Label(meta,text='Supplier').grid(row=0,column=0,padx=(0,12),sticky='w')
        self.supplier_labels = [f'{row["name"]} (#{row["id"]})' for row in self.suppliers]
        self.supplier_select = ttk.Combobox(meta,values=self.supplier_labels,state='readonly',width=45)
        self.supplier_select.grid(row=0,column=1,sticky='ew',pady=3)
        self.supplier_select.bind('<<ComboboxSelected>>',self.supplier_changed)
        ttk.Label(meta,text='Notes').grid(row=1,column=0,padx=(0,12),sticky='nw',pady=(7,0))
        self.notes = tk.Text(meta,height=2,wrap='word',undo=True,relief='solid',bd=1)
        self.notes.grid(row=1,column=1,sticky='ew',pady=(7,0))
        if self.existing:
            self.notes.insert('1.0',self.existing['notes'] or '')
            idx=next((i for i,r in enumerate(self.suppliers) if r['id']==self.supplier_id),-1)
            if idx>=0:self.supplier_select.current(idx)
            self.supplier_select.configure(state='disabled')
            ttk.Label(meta,text='Supplier is locked on existing orders; create a new PO for another supplier.').grid(
                row=2,column=1,sticky='w')

        controls = ttk.Frame(content)
        controls.grid(row=2,column=0,sticky='ew',pady=(4,12))
        controls.columnconfigure(0,weight=1)
        ttk.Label(controls,text='Supplier product').grid(row=0,column=0,sticky='w')
        ttk.Label(controls,text='Quantity').grid(row=0,column=1,sticky='w',padx=(10,0))
        ttk.Label(controls,text='Unit cost ($)').grid(row=0,column=2,sticky='w',padx=(10,0))
        self.product_select = ttk.Combobox(controls,state='readonly',width=50)
        self.product_select.grid(row=1,column=0,sticky='ew',pady=(3,5))
        self.product_select.bind('<<ComboboxSelected>>',self.product_changed)
        self.quantity = tk.StringVar(value='1')
        self.unit_cost = tk.StringVar()
        self.quantity_entry = ttk.Entry(controls,textvariable=self.quantity,width=11)
        self.quantity_entry.grid(row=1,column=1,padx=(10,0),sticky='ew',pady=(3,5))
        self.cost_entry = ttk.Entry(controls,textvariable=self.unit_cost,width=15)
        self.cost_entry.grid(row=1,column=2,padx=(10,0),sticky='ew',pady=(3,5))
        ttk.Button(controls,text='Add Product',command=self.add_product).grid(row=1,column=3,padx=(12,0))
        ttk.Button(controls,text='Update Selected Line',command=self.update_selected).grid(row=2,column=0,sticky='w',pady=(5,0))
        ttk.Button(controls,text='Remove Selected Line',command=self.remove_selected).grid(row=2,column=1,columnspan=2,sticky='w',padx=(10,0),pady=(5,0))

        table_frame = ttk.Frame(content)
        table_frame.grid(row=3,column=0,sticky='nsew')
        table_frame.rowconfigure(0,weight=1)
        table_frame.columnconfigure(0,weight=1)
        self.table = ttk.Treeview(table_frame,columns=('SKU','Product','Quantity','Unit cost','Line total'),
                                  show='headings',selectmode='browse')
        for name,width,anchor in [('SKU',125,'w'),('Product',290,'w'),('Quantity',100,'e'),
                                   ('Unit cost',130,'e'),('Line total',140,'e')]:
            self.table.heading(name,text=name)
            self.table.column(name,width=width,minwidth=70,anchor=anchor)
        self.table.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=self.table.yview)
        scroll.grid(row=0,column=1,sticky='ns')
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',self.line_selected)
        self.table.bind('<Double-1>',self.edit_focus)
        self.table.bind('<Delete>',lambda event:self.remove_selected())

        footer=ttk.Frame(content)
        footer.grid(row=4,column=0,sticky='ew',pady=(12,0))
        footer.columnconfigure(0,weight=1)
        self.order_total = ttk.Label(footer,text='Order total: $0.00',font=('Segoe UI',12,'bold'))
        self.order_total.grid(row=0,column=0,sticky='w')
        actions=ttk.Frame(footer)
        actions.grid(row=0,column=1,sticky='e')
        ttk.Button(actions,text='Cancel',command=self.cancel).pack(side='right',padx=(8,0))
        self.save_button=ttk.Button(actions,text='Save Changes' if po_id else 'Save Purchase Order',
                                    command=self.save,style='Accent.TButton')
        self.save_button.pack(side='right')

        self.load_products()
        self.refresh_lines()
        self.window.grab_set()
        self.window.lift()
        self.window.wait_window()

    def supplier_changed(self, event=None):
        index=self.supplier_select.current()
        if index<0:return
        new_supplier=self.suppliers[index]['id']
        if self.supplier_id is not None and new_supplier != self.supplier_id and self.lines:
            if not messagebox.askyesno('Change supplier?',
                    'Changing suppliers will clear the items currently added to this order. Continue?',
                    parent=self.window):
                old_index=next(i for i,r in enumerate(self.suppliers) if r['id']==self.supplier_id)
                self.supplier_select.current(old_index)
                return
            self.lines.clear()
            self.refresh_lines()
        self.supplier_id = new_supplier
        self.load_products()

    def load_products(self):
        self.products=[]
        if self.supplier_id is not None:
            self.products=products_for_supplier(self.db,self.supplier_id)
            if self.original_products:
                existing={p['id'] for p in self.products}
                for pid in sorted(self.original_products-existing):
                    historical=self.db.execute(
                        'SELECT id,sku,name,cost,qty FROM products WHERE id=?',(pid,)).fetchone()
                    if historical:self.products.append(historical)
        self.product_labels=[f'{p["sku"]} — {p["name"]}' for p in self.products]
        self.product_select.configure(values=self.product_labels)
        self.product_select.set('')
        self.unit_cost.set('')

    def product_changed(self,event=None):
        index=self.product_select.current()
        if index>=0:
            product=self.products[index]
            self.unit_cost.set(f'{product["cost"]/100:.2f}')

    def validate_inputs(self):
        try:
            qty=int(self.quantity.get().strip())
        except (ValueError,TypeError):
            raise ValueError('Quantity must be a positive whole number.') from None
        if qty<=0 or qty>100000000:
            raise ValueError('Quantity must be between 1 and 100,000,000.')
        cost=cents(self.unit_cost.get())
        if cost>10000000000:
            raise ValueError('Unit cost exceeds the allowed amount.')
        return qty,cost

    def add_product(self):
        index=self.product_select.current()
        if index<0:
            messagebox.showwarning('Select a product','Choose a supplier product first.',parent=self.window)
            return
        product=self.products[index]
        pid=product['id']
        if pid in self.lines:
            self.table.selection_set(str(pid))
            self.table.see(str(pid))
            messagebox.showinfo('Already on PO','This product is already listed. Select its row, adjust the quantity or cost, and click Update Selected Line.',parent=self.window)
            return
        if pid in self.original_products and product['id'] not in {p['id'] for p in products_for_supplier(self.db,self.supplier_id)}:
            messagebox.showwarning('Product reassigned','This product is no longer assigned to this supplier and cannot be re-added.',parent=self.window)
            return
        try:qty,cost=self.validate_inputs()
        except ValueError as exc:
            messagebox.showerror('Invalid PO item',str(exc),parent=self.window);return
        self.lines[pid]=(qty,cost)
        self.refresh_lines(select=pid)

    def line_selected(self,event=None):
        selected=self.table.selection()
        if not selected:return
        pid=int(selected[0])
        qty,cost=self.lines[pid]
        self.quantity.set(str(qty))
        self.unit_cost.set(f'{cost/100:.2f}')
        for i,product in enumerate(self.products):
            if product['id']==pid:
                self.product_select.current(i)
                break

    def edit_focus(self,event=None):
        if self.table.selection():self.quantity_entry.focus_set()

    def update_selected(self):
        selected=self.table.selection()
        if not selected:
            messagebox.showwarning('Select an item','Select a PO line to correct its quantity or unit cost.',parent=self.window)
            return
        try:qty,cost=self.validate_inputs()
        except ValueError as exc:
            messagebox.showerror('Invalid PO item',str(exc),parent=self.window);return
        pid=int(selected[0])
        self.lines[pid]=(qty,cost)
        self.refresh_lines(select=pid)

    def remove_selected(self):
        selected=self.table.selection()
        if not selected:return
        pid=int(selected[0])
        del self.lines[pid]
        self.refresh_lines()
        self.quantity.set('1')
        self.unit_cost.set('')

    def refresh_lines(self,select=None):
        self.table.delete(*self.table.get_children())
        total=0
        for pid,(qty,cost) in self.lines.items():
            product=self.db.execute('SELECT sku,name FROM products WHERE id=?',(pid,)).fetchone()
            if not product:continue
            total+=qty*cost
            self.table.insert('','end',iid=str(pid),values=(product['sku'],product['name'],qty,
                                                         money(cost),money(qty*cost)))
        self.order_total.configure(text=f'Order total: {money(total)}')
        if select is not None and self.table.exists(str(select)):
            self.table.selection_set(str(select))
            self.table.see(str(select))

    def save(self):
        if self.supplier_id is None:
            messagebox.showwarning('Select a supplier','Choose a supplier before saving.',parent=self.window)
            self.supplier_select.focus_set()
            return
        if not self.lines:
            messagebox.showwarning('Empty purchase order','Add at least one product before saving.',parent=self.window)
            return
        notes=self.notes.get('1.0','end-1c').strip()
        items=[(pid,qty,cost) for pid,(qty,cost) in self.lines.items()]
        try:
            if self.po_id is None:
                saved=create_supplier_po(self.db,self.supplier_id,notes,items)
            else:
                saved=update_supplier_po(self.db,self.po_id,notes,items)
        except Exception as exc:
            messagebox.showerror('Purchase order not saved',str(exc),parent=self.window)
            return
        self.saved_id=saved
        self.window.destroy()

    def cancel(self):
        self.window.destroy()


def open_purchase_order_editor(parent,db,po_id=None):
    """Show modal PO editor; returns saved PO id or None if cancelled."""
    editor=PurchaseOrderEditor(parent,db,po_id=po_id)
    return editor.saved_id
