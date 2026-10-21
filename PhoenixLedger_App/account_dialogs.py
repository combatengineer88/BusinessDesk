"""Fixed-footer dialogs for partial PO receipts and customer/supplier accounts."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from core_v1 import cents, money
from account_workflows import (po_lines, receive_po, po_balance, record_supplier_payment,
                               credit_info, configure_credit, charge_existing_invoice, apply_credit_payment)


def _handle(parent,callback):
    try:callback()
    except (ValueError,TypeError) as exc:messagebox.showerror('Transaction not saved',str(exc),parent=parent)


def receive_partial_dialog(parent,db,po_id):
    records=po_lines(db,po_id)
    if not records:raise ValueError('This PO has no line items.')
    po=db.execute('SELECT status FROM purchase_orders WHERE id=?',(po_id,)).fetchone()
    if po is None or po['status'] not in ('Open','Partially Received'):
        raise ValueError('Order is already fully received.')
    win=tk.Toplevel(parent);win.title(f'Receive PO #{po_id}')
    win.transient(parent);win.grab_set();win.geometry('860x515');win.minsize(540,380)
    footer=ttk.Frame(win,padding=12);footer.pack(side='bottom',fill='x')
    body=ttk.Frame(win,padding=(14,12));body.pack(fill='both',expand=True)
    ttk.Label(body,text=f'Receive Purchase Order #{po_id}',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='Enter quantities delivered in this shipment. Unreceived items remain available for later receipts.',
              wraplength=760).pack(anchor='w',pady=(4,10))
    grid=ttk.Frame(body);grid.pack(fill='both',expand=True)
    tree=ttk.Treeview(grid,columns=('Product','Ordered','Received','Remaining','This shipment'),show='headings')
    for col,w in [('Product',300),('Ordered',100),('Received',100),('Remaining',100),('This shipment',120)]:
        tree.heading(col,text=col);tree.column(col,width=w,anchor='w')
    scroll=ttk.Scrollbar(grid,orient='vertical',command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
    entry_row=ttk.Frame(body);entry_row.pack(fill='x',pady=9)
    ttk.Label(entry_row,text='Selected line, quantity received now:').pack(side='left')
    qty=tk.StringVar(value='0');ttk.Entry(entry_row,textvariable=qty,width=12).pack(side='left',padx=8)
    new_qty={line['id']:0 for line in records}
    indexed={line['id']:line for line in records}
    def repaint():
        tree.delete(*tree.get_children())
        for line in records:
            tree.insert('','end',iid=str(line['id']),values=(line['name'],line['qty'],line['received_qty'],
                       line['qty']-line['received_qty'],new_qty[line['id']]))
    def choose(_=None):
        if tree.selection():qty.set(str(new_qty[int(tree.selection()[0])]))
    def update():
        if not tree.selection():raise ValueError('Select a PO line first.')
        line_id=int(tree.selection()[0])
        typed=qty.get().strip()
        if not typed.isdecimal():raise ValueError('Enter a nonnegative whole-number quantity.')
        value=int(typed)
        line=indexed[line_id]
        if value>line['qty']-line['received_qty']:
            raise ValueError('Received quantity exceeds the remaining ordered quantity.')
        new_qty[line_id]=value
        repaint();tree.selection_set(str(line_id))
    def fill():
        for line in records:new_qty[line['id']]=line['qty']-line['received_qty']
        repaint()
    def save():
        if tree.selection() and qty.get().strip()!=str(new_qty[int(tree.selection()[0])]):update()
        receipt,status=receive_po(db,po_id,new_qty)
        win.destroy()
        messagebox.showinfo('Receipt saved',f'Receipt #{receipt} saved; PO status: {status}.',parent=parent)
    ttk.Button(entry_row,text='Update selected line',command=lambda:_handle(win,update)).pack(side='left',padx=5)
    ttk.Button(entry_row,text='Fill all remaining',command=fill).pack(side='left',padx=5)
    ttk.Button(footer,text='Cancel',command=win.destroy).pack(side='right',padx=5)
    ttk.Button(footer,text='Save receipt',style='Accent.TButton',command=lambda:_handle(win,save)).pack(side='right',padx=5)
    tree.bind('<<TreeviewSelect>>',choose)
    repaint();win.wait_window()


def supplier_payment_dialog(parent,db,po_id,form):
    due=po_balance(db,po_id)
    if due<=0:raise ValueError('No unpaid balance exists for received goods on this PO.')
    v=form('Record supplier payment', [('amount',f'Amount owed: {money(due)}'),
             ('method','Payment method'),('reference','Check / confirmation number')],
           {'amount':f'{due/100:.2f}','method':'Bank transfer'})
    if not v:return False
    payment=record_supplier_payment(db,po_id,cents(v['amount']),v['method'],v['reference'])
    messagebox.showinfo('Supplier payment saved',f'Payment #{payment} recorded for PO #{po_id}.',parent=parent)
    return True


def credit_manager_dialog(parent,db,customer_id,form):
    customer=db.execute('SELECT name FROM customers WHERE id=?',(customer_id,)).fetchone()
    if not customer:raise ValueError('Customer not found.')
    win=tk.Toplevel(parent);win.title('Customer credit — '+customer['name'])
    win.transient(parent);win.grab_set();win.geometry('820x560');win.minsize(550,400)
    footer=ttk.Frame(win,padding=12);footer.pack(side='bottom',fill='x')
    body=ttk.Frame(win,padding=(14,12));body.pack(fill='both',expand=True)
    ttk.Label(body,text='Customer Credit — '+customer['name'],style='Section.TLabel').pack(anchor='w')
    stats=ttk.Label(body);stats.pack(anchor='w',pady=(6,12))
    info=credit_info(db,customer_id)
    enabled=tk.BooleanVar(value=info['enabled'])
    limit=tk.StringVar(value=f"{info['limit']/100:.2f}")
    terms=tk.StringVar(value=str(info['terms_days']))
    fields=ttk.Frame(body);fields.pack(fill='x')
    ttk.Checkbutton(fields,text='Account enabled',variable=enabled).grid(row=0,column=0,sticky='w')
    ttk.Label(fields,text='Limit ($)').grid(row=0,column=1,sticky='w',padx=(18,3))
    ttk.Entry(fields,textvariable=limit,width=13).grid(row=0,column=2,sticky='w')
    ttk.Label(fields,text='Net days').grid(row=0,column=3,sticky='w',padx=(18,3))
    ttk.Entry(fields,textvariable=terms,width=8).grid(row=0,column=4,sticky='w')
    columns=('Invoice ID','Date','Due','Total','Paid','Balance')
    table=ttk.Treeview(body,columns=columns,show='headings',height=10)
    for col,width in zip(columns,(90,95,95,120,120,120)):
        table.heading(col,text=col);table.column(col,width=width,anchor='w')
    table.pack(fill='both',expand=True,pady=(12,7))
    ttk.Label(body,text='Account payments apply to the oldest on-account invoices first. '
                      'Revenue and receivables are posted by the normal invoice workflow.',wraplength=730).pack(anchor='w')
    def refresh():
        current=credit_info(db,customer_id)
        stats.configure(text=f"Credit limit: {money(current['limit'])}     Outstanding: {money(current['used'])}     Available: {money(current['available'])}")
        table.delete(*table.get_children())
        for row in db.execute('''SELECT d.id,d.created,d.credit_due_on,d.total,
                  coalesce((SELECT sum(p.amount) FROM payments p WHERE p.document_id=d.id),0) AS paid
                  FROM documents d WHERE d.kind='Invoice' AND d.credit_account=1 AND d.customer_id=?
                  ORDER BY d.created DESC,d.id DESC''',(customer_id,)):
            table.insert('','end',values=(row['id'],row['created'],row['credit_due_on'],money(row['total']),money(row['paid']),money(row['total']-row['paid'])))
    def save_settings():
        configure_credit(db,customer_id,bool(enabled.get()),cents(limit.get()),int(terms.get()))
        refresh();messagebox.showinfo('Saved','Customer credit settings saved.',parent=win)
    def charge():
        inv=simpledialog.askinteger('Charge an existing invoice','Invoice ID:',parent=win,minvalue=1)
        if inv is None:return
        belongs=db.execute('SELECT customer_id FROM documents WHERE id=?',(inv,)).fetchone()
        if not belongs or belongs[0]!=customer_id:raise ValueError('That invoice does not belong to this customer.')
        charge_existing_invoice(db,inv)
        refresh();messagebox.showinfo('Credit charge saved','Invoice is now on the credit account.',parent=win)
    def receive_payment():
        owed=credit_info(db,customer_id)['used']
        if owed<=0:raise ValueError('No outstanding account balance.')
        v=form('Receive account payment',[('amount',f'Amount owed: {money(owed)}'),('method','Payment method')],
               {'amount':f'{owed/100:.2f}','method':'Bank transfer'})
        # Nested payment form has its own grab; restore the credit manager's grab.
        if win.winfo_exists():win.grab_set()
        if not v:return
        applied=apply_credit_payment(db,customer_id,cents(v['amount']),v['method'])
        refresh();messagebox.showinfo('Payment saved',f'Payment allocated to {len(applied)} invoice(s).',parent=win)
    ttk.Button(footer,text='Close',command=win.destroy).pack(side='right',padx=4)
    ttk.Button(footer,text='Save credit settings',style='Accent.TButton',command=lambda:_handle(win,save_settings)).pack(side='right',padx=4)
    ttk.Button(footer,text='Record payment',command=lambda:_handle(win,receive_payment)).pack(side='left',padx=4)
    ttk.Button(footer,text='Charge existing invoice',command=lambda:_handle(win,charge)).pack(side='left',padx=4)
    refresh();win.wait_window()
