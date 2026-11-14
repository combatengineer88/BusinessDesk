"""UI for selected-product sticker batches. This window contains no business writes."""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from inventory_labels import LABEL_FORMATS, render_label_sheet, get_label_products


def open_barcode_print_dialog(parent, db, selected_ids):
    ids=list(dict.fromkeys(int(x) for x in selected_ids))
    selected = get_label_products(db,[(id,1) for id in ids])
    win=tk.Toplevel(parent)
    win.title('PhoenixLedger | Print Barcode Stickers')
    win.transient(parent)
    win.geometry('820x530')
    win.minsize(630,390)
    win.grab_set()
    footer=ttk.Frame(win,padding=(18,10,18,14));footer.pack(side='bottom',fill='x')
    body=ttk.Frame(win,padding=(18,12,18,3));body.pack(fill='both',expand=True)
    ttk.Label(body,text='Barcode sticker printing',font=('Segoe UI',16,'bold')).pack(anchor='w')
    ttk.Label(body,text='Set the number of labels for each product, choose the sticker sheet, then save the PDF or open it for printing.',
              wraplength=760).pack(anchor='w',pady=(4,12))
    cols=('Product','SKU','Barcode source','Labels')
    frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
    frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
    tree=ttk.Treeview(frame,columns=cols,show='headings',height=5,selectmode='browse')
    for name,width in [('Product',315),('SKU',135),('Barcode source',135),('Labels',90)]:
        tree.heading(name,text=name)
        tree.column(name,width=width,anchor='w' if name != 'Labels' else 'center',stretch=True)
    tree.grid(row=0,column=0,sticky='nsew')
    scrollbar=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
    scrollbar.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scrollbar.set)
    quantities={}
    for product,_ in selected:
        pid=product['id'];quantities[pid]=1
        tree.insert('', 'end',iid=str(pid), values=(product['name'],product['sku'],product['source'],1))
    controls=ttk.Frame(body,padding=(0,8,0,3));controls.pack(fill='x')
    ttk.Label(controls,text='Selected product label count:').pack(side='left',padx=(0,7))
    copies=tk.StringVar(value='1')
    copy_input=ttk.Spinbox(controls,from_=1,to=500,width=7,textvariable=copies)
    copy_input.pack(side='left')
    def set_qty():
        sel=tree.selection()
        if not sel:raise ValueError('Select a product row first.')
        try:qty=int(copies.get())
        except ValueError:raise ValueError('Labels must be a whole number.')
        if not 1<=qty<=500:raise ValueError('Choose 1 to 500 labels per product.')
        pid=int(sel[0]);quantities[pid]=qty
        product=tree.item(sel[0],'values')
        tree.item(sel[0],values=(*product[:3],qty))
        update_total()
    def try_set_qty():
        try:set_qty()
        except ValueError as exc:messagebox.showerror('Sticker quantity',str(exc),parent=win)
    ttk.Button(controls,text='Update quantity',command=try_set_qty).pack(side='left',padx=8)
    ttk.Label(controls,text='Total labels:').pack(side='left',padx=(18,5))
    total=tk.StringVar(value=str(len(quantities)))
    ttk.Label(controls,textvariable=total,font=('Segoe UI',10,'bold')).pack(side='left')
    def update_total():total.set(str(sum(quantities.values())))
    def on_select(_=None):
        s=tree.selection()
        if s:copies.set(str(quantities[int(s[0])]))
    tree.bind('<<TreeviewSelect>>',on_select)
    tree.bind('<Double-1>',lambda e:(copy_input.focus_set(),copy_input.selection_range(0,'end')))
    if ids:tree.selection_set(str(ids[0]));on_select()
    options=ttk.Frame(body,padding=(0,11,0,10));options.pack(fill='x')
    ttk.Label(options,text='Sheet format').grid(row=0,column=0,sticky='w',padx=(0,6),pady=5)
    fmt=tk.StringVar(value=next(iter(LABEL_FORMATS)))
    ttk.Combobox(options,textvariable=fmt,values=list(LABEL_FORMATS),state='readonly',width=43).grid(row=0,column=1,sticky='w',pady=5)
    ttk.Label(options,text='Start at label').grid(row=1,column=0,sticky='w',padx=(0,6),pady=5)
    start=tk.StringVar(value='1')
    first=ttk.Spinbox(options,from_=1,to=30,width=7,textvariable=start)
    first.grid(row=1,column=1,sticky='w',pady=5)
    ttk.Label(options,text='(for a partially used sheet)').grid(row=1,column=2,sticky='w',padx=8)
    show_price=tk.BooleanVar(value=True)
    ttk.Checkbutton(options,text='Include selling price',variable=show_price).grid(row=2,column=1,sticky='w',pady=(5,0))
    def on_format(*_):
        layout=LABEL_FORMATS[fmt.get()]
        slots=layout['rows']*layout['cols']
        first.configure(to=slots)
        try:
            if int(start.get())>slots:start.set('1')
        except ValueError:start.set('1')
    fmt.trace_add('write',on_format)
    ttk.Label(body,text='Print using Letter paper, 100% / Actual Size, with scaling and Fit-to-page disabled.',
              foreground='#475569',wraplength=750).pack(anchor='w',pady=(0,6))
    def make_pdf(open_to_print=False):
        try:
            # Apply the pending quantity even if Update was not clicked.
            if tree.selection():set_qty()
            filename=filedialog.asksaveasfilename(parent=win,defaultextension='.pdf',
                initialfile='PhoenixLedger_Barcode_Stickers.pdf',filetypes=[('PDF files','*.pdf')])
            if not filename:return
            render_label_sheet(db,list(quantities.items()),filename,fmt.get(),int(start.get()),show_price.get())
            if open_to_print:
                if os.name=='nt':os.startfile(str(Path(filename)))
                else:messagebox.showinfo('Saved',f'Sticker PDF saved to:\n{filename}\n\nOpen this file in your PDF viewer and print at 100% / Actual Size.',parent=win)
            else:messagebox.showinfo('Saved',f'Sticker PDF saved to:\n{filename}',parent=win)
        except Exception as exc:messagebox.showerror('Barcode sticker printing',str(exc),parent=win)
    ttk.Button(footer,text='Cancel',command=win.destroy).pack(side='left')
    ttk.Button(footer,text='Save PDF',command=lambda:make_pdf(False)).pack(side='right',padx=(9,0))
    ttk.Button(footer,text='Save & Open to Print',command=lambda:make_pdf(True)).pack(side='right')
    win.bind('<Escape>',lambda e:win.destroy())
    win.wait_window()
