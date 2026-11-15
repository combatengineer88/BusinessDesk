"""Interactive PhoenixLedger inventory dialogs (Tkinter, offline)."""
from __future__ import annotations

import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from core_v1 import money
from inventory_management import (STOCK_MODES, lookup_scan,adjust_stock,update_policy,
    movements,reorder_recommendations,create_reorder_drafts)


def _window(parent, title, size='850x600'):
    win=tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.resizable(True,True)
    sw=max(600,win.winfo_screenwidth()-100)
    sh=max(420,win.winfo_screenheight()-120)
    desired_w,desired_h=map(int,size.split('x'))
    w=min(desired_w,sw);h=min(desired_h,sh)
    win.geometry(f'{w}x{h}')
    win.minsize(min(550,w),min(350,h))
    return win


def scan_to_adjust(parent, db, actor='', initial_code=''):
    """Barcode scanners act as keyboard input and typically send Enter at the end."""
    win=_window(parent,'Scan to Adjust Inventory','760x550')
    frame=ttk.Frame(win,padding=18);frame.pack(fill='both',expand=True)
    frame.columnconfigure(1,weight=1)
    row=0
    ttk.Label(frame,text='Scan to Adjust',style='Section.TLabel').grid(row=row,column=0,columnspan=2,sticky='w',pady=(0,6));row+=1
    ttk.Label(frame,text='Scan a barcode (or type an SKU) and press Enter. Adjustments save to the inventory history.',
              wraplength=680).grid(row=row,column=0,columnspan=2,sticky='w',pady=(0,10));row+=1
    ttk.Label(frame,text='Barcode / SKU').grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
    scan=tk.StringVar(value=initial_code)
    entry=ttk.Entry(frame,textvariable=scan)
    entry.grid(row=row,column=1,sticky='ew',pady=5);row+=1
    product_title=tk.StringVar(value='No product scanned yet')
    on_hand=tk.StringVar(value='')
    ttk.Label(frame,textvariable=product_title,font=('Segoe UI',13,'bold'),wraplength=610).grid(
        row=row,column=0,columnspan=2,sticky='w',pady=(9,3));row+=1
    ttk.Label(frame,textvariable=on_hand).grid(row=row,column=0,columnspan=2,sticky='w',pady=(0,9));row+=1
    selected={'product_id':None}
    operation=tk.StringVar(value='Add')
    quantity=tk.StringVar(value='1')
    reason=tk.StringVar(value='Physical count correction')
    ttk.Label(frame,text='Action').grid(row=row,column=0,sticky='w',pady=6)
    action=ttk.Combobox(frame,values=['Add','Remove','Set'],textvariable=operation,state='readonly')
    action.grid(row=row,column=1,sticky='ew',pady=6);row+=1
    ttk.Label(frame,text='Quantity').grid(row=row,column=0,sticky='w',pady=6)
    ttk.Entry(frame,textvariable=quantity).grid(row=row,column=1,sticky='ew',pady=6);row+=1
    ttk.Label(frame,text='Reason').grid(row=row,column=0,sticky='w',pady=6)
    reasons=('Physical count correction','Damaged / scrap','Return to inventory',
             'Sample / internal use','Lost / shrinkage','Other')
    ttk.Combobox(frame,textvariable=reason,values=reasons).grid(row=row,column=1,sticky='ew',pady=6);row+=1
    status=tk.StringVar(value='')
    ttk.Label(frame,textvariable=status,wraplength=650).grid(row=row,column=0,columnspan=2,sticky='w',pady=10);row+=1
    frame.rowconfigure(row,weight=1)
    bottom=ttk.Frame(frame);bottom.grid(row=row+1,column=0,columnspan=2,sticky='ew',pady=(12,0))
    bottom.columnconfigure(0,weight=1)

    def locate(event=None):
        try:
            p=lookup_scan(db,scan.get())
        except ValueError as exc:
            selected['product_id']=None
            product_title.set('No matching product')
            on_hand.set('')
            status.set(str(exc))
            return
        selected['product_id']=p['id']
        product_title.set(f"{p['name']}  |  {p['sku']}")
        on_hand.set(f"On hand: {p['qty']}     Barcode: {p['barcode'] or '—'}")
        status.set('Ready to adjust. Choose Add, Remove or Set; then save.')
    def save(event=None):
        try:
            product_id=selected['product_id']
            if product_id is None:raise ValueError('Scan or look up a product first.')
            val=quantity.get().strip()
            if not val.isdecimal():raise ValueError('Enter a whole-number quantity.')
            before,after=adjust_stock(db,product_id,operation.get(),int(val),reason.get(),actor)
        except Exception as exc:
            messagebox.showerror('Inventory adjustment',str(exc),parent=win)
            return
        status.set(f'Saved stock adjustment: {before} → {after}. Scan the next product.')
        selected['product_id']=None
        product_title.set('Ready for next barcode')
        on_hand.set('')
        scan.set('');quantity.set('1')
        entry.focus_set()
        if callable(getattr(win,'on_inventory_changed',None)):
            win.on_inventory_changed()
    ttk.Button(bottom,text='Close',command=win.destroy).pack(side='right',padx=(10,0))
    ttk.Button(bottom,text='Save Adjustment',command=save,style='Accent.TButton').pack(side='right')
    ttk.Button(bottom,text='Find Product',command=locate).pack(side='right',padx=(0,10))
    entry.bind('<Return>',locate)
    win.bind('<Control-s>',save)
    win.after(100,entry.focus_set)
    if initial_code:win.after(150,locate)
    win.grab_set()
    return win


def show_history(parent,db,product_id=None):
    win=_window(parent,'Inventory Movement History','1050x580')
    outer=ttk.Frame(win,padding=12);outer.pack(fill='both',expand=True)
    ttk.Label(outer,text='Inventory movement history',style='Section.TLabel').pack(anchor='w',pady=(0,10))
    cols=('Date / UTC','SKU','Product','Before','Change','After','Source','Reason','User')
    wrap=ttk.Frame(outer);wrap.pack(fill='both',expand=True)
    wrap.rowconfigure(0,weight=1);wrap.columnconfigure(0,weight=1)
    tree=ttk.Treeview(wrap,columns=cols,show='headings')
    widths=(144,115,190,66,66,66,130,220,90)
    for col,width in zip(cols,widths):
        tree.heading(col,text=col);tree.column(col,width=width,anchor='w',stretch=False)
    tree.grid(row=0,column=0,sticky='nsew')
    vbar=ttk.Scrollbar(wrap,orient='vertical',command=tree.yview)
    hbar=ttk.Scrollbar(wrap,orient='horizontal',command=tree.xview)
    vbar.grid(row=0,column=1,sticky='ns')
    hbar.grid(row=1,column=0,sticky='ew')
    tree.configure(yscrollcommand=vbar.set,xscrollcommand=hbar.set)
    records=[]
    def refresh():
        nonlocal records
        records=movements(db,product_id,limit=2000)
        tree.delete(*tree.get_children())
        for m in records:
            tree.insert('','end',values=(m['changed_at'],m['sku'],m['name'],m['old_qty'],
                ('+' if m['change_qty']>0 else '')+str(m['change_qty']),m['new_qty'],
                m['source'],m['reason'],m['actor']))
    footer=ttk.Frame(outer);footer.pack(fill='x',pady=(10,0))
    def export():
        path=filedialog.asksaveasfilename(parent=win,defaultextension='.csv',
            initialfile='PhoenixLedger_Inventory_Movements.csv',filetypes=[('CSV spreadsheet','*.csv')])
        if not path:return
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(cols)
            for m in records:
                writer.writerow((m['changed_at'],m['sku'],m['name'],m['old_qty'],m['change_qty'],
                    m['new_qty'],m['source'],m['reason'],m['actor']))
        messagebox.showinfo('Export complete','Inventory history exported.',parent=win)
    ttk.Button(footer,text='Export History CSV',command=export).pack(side='left')
    ttk.Button(footer,text='Refresh',command=refresh).pack(side='left',padx=8)
    ttk.Button(footer,text='Close',command=win.destroy).pack(side='right')
    refresh();return win


def configure_inventory_policy(parent,db,ids,refresh=None):
    ids=list(dict.fromkeys(ids))
    if not ids:raise ValueError('Select one or more products to configure.')
    first=db.execute('SELECT * FROM products WHERE id=?',(ids[0],)).fetchone()
    if first is None:raise ValueError('Product not found.')
    win=_window(parent,f'Inventory Policy — {len(ids)} Product(s)','570x405')
    form=ttk.Frame(win,padding=18);form.pack(fill='both',expand=True)
    form.columnconfigure(1,weight=1)
    ttk.Label(form,text='Stock & Reorder Settings',style='Section.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
    ttk.Label(form,text=f'{len(ids)} selected products. Saving applies these settings to all selected products.',
              wraplength=480).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
    point=tk.StringVar(value=str(first['reorder_point']))
    batch=tk.StringVar(value=str(first['reorder_qty']))
    mode=tk.StringVar(value=str(first['stock_mode']))
    bin_var=tk.StringVar(value=str(first['bin_location'] or ''))
    for idx,(name,var) in enumerate([('Reorder at or below',point),('Reorder batch quantity',batch),('Shelf / bin',bin_var)],2):
        ttk.Label(form,text=name).grid(row=idx,column=0,sticky='w',padx=(0,12),pady=7)
        ttk.Entry(form,textvariable=var).grid(row=idx,column=1,sticky='ew',pady=7)
    ttk.Label(form,text='Item type').grid(row=5,column=0,sticky='w',pady=7)
    ttk.Combobox(form,values=STOCK_MODES,textvariable=mode,state='readonly').grid(row=5,column=1,sticky='ew',pady=7)
    ttk.Label(form,text='Only stocked items are considered for low-stock reordering.',
              wraplength=490).grid(row=6,column=0,columnspan=2,sticky='w',pady=(8,0))
    buttons=ttk.Frame(form);buttons.grid(row=7,column=0,columnspan=2,sticky='e',pady=(20,0))
    def save():
        try:
            if not point.get().strip().isdecimal() or not batch.get().strip().isdecimal():
                raise ValueError('Reorder quantities must be whole numbers >= 0.')
            update_policy(db,ids,int(point.get()),int(batch.get()),mode.get(),bin_var.get())
        except ValueError as exc:
            messagebox.showerror('Reorder settings',str(exc),parent=win);return
        win.destroy()
        if refresh:refresh()
    ttk.Button(buttons,text='Cancel',command=win.destroy).pack(side='right',padx=(10,0))
    ttk.Button(buttons,text='Save Policy',command=save,style='Accent.TButton').pack(side='right')
    win.grab_set();return win


def review_reorders(parent,db,on_created=None):
    win=_window(parent,'Suggested Reorders — Draft Purchase Orders','1050x620')
    frame=ttk.Frame(win,padding=15);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Review Suggested Reorders',style='Section.TLabel').pack(anchor='w',pady=(0,8))
    ttk.Label(frame,text='Suggestions account for pending quantities on Draft, Open and Partially Received POs. '
              'Creating a draft does not order or receive stock.',wraplength=960).pack(anchor='w',pady=(0,12))
    columns=('Supplier','SKU','Product','On hand','On order','Reorder at','Suggested','Unit cost')
    table_frame=ttk.Frame(frame);table_frame.pack(fill='both',expand=True)
    table_frame.rowconfigure(0,weight=1);table_frame.columnconfigure(0,weight=1)
    tree=ttk.Treeview(table_frame,columns=columns,show='headings')
    for name,width in zip(columns,(155,120,210,75,80,90,85,110)):
        tree.heading(name,text=name);tree.column(name,width=width,stretch=False)
    tree.grid(row=0,column=0,sticky='nsew')
    sc=ttk.Scrollbar(table_frame,orient='vertical',command=tree.yview)
    sc.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=sc.set)
    status=tk.StringVar()
    ttk.Label(frame,textvariable=status,wraplength=970).pack(anchor='w',pady=(10,6))
    current=[]
    def refresh():
        nonlocal current
        current=reorder_recommendations(db)
        tree.delete(*tree.get_children())
        for r in current:
            tree.insert('','end',values=(r['supplier_name'] or 'UNASSIGNED',r['sku'],r['name'],
                r['qty'],r['on_order'],r['reorder_point'],r['suggested_qty'],money(r['cost'])))
        count=sum(1 for r in current if r['supplier_id'] is None)
        status.set(f'{len(current)} suggested item(s); {count} require a supplier assignment before a PO can be created.')
    def create():
        if not current:
            messagebox.showinfo('Reorders','No unfulfilled reorder needs were found.',parent=win);return
        if not messagebox.askyesno('Create draft purchase orders?',
                'Create editable Draft purchase orders grouped by supplier? '
                'They will NOT be submitted or affect inventory until you approve and receive them.',parent=win):
            return
        created,missing=create_reorder_drafts(db)
        if on_created:on_created()
        refresh()
        ids=', '.join('#'+str(i) for i in created) or 'none'
        messagebox.showinfo('Draft purchase orders',
            f'Created: {ids}\nProducts without a supplier: {len(missing)}\n'
            'Go to Purchase Orders, edit each Draft, and click Approve Draft PO.',parent=win)
    footer=ttk.Frame(frame);footer.pack(fill='x')
    ttk.Button(footer,text='Refresh',command=refresh).pack(side='left')
    ttk.Button(footer,text='Close',command=win.destroy).pack(side='right',padx=(8,0))
    ttk.Button(footer,text='Create Draft POs',command=create,style='Accent.TButton').pack(side='right')
    refresh();win.grab_set();return win
