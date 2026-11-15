"""Responsive bulk purchasing/pricing editor for PhoenixLedger Products tab."""
import tkinter as tk
from tkinter import ttk, messagebox
from core_v1 import cents, money
from inventory_costing import (rounded_cents,set_bulk_quote,set_manual_cost,margin_info,
    price_tiers,set_price_tier,delete_price_tier,cost_history,update_pack_rules)


def open_bulk_pricing_dialog(parent,db,product_id,actor='',on_saved=None):
    p=db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
    if p is None:raise ValueError('Choose a product to configure pricing.')
    win=tk.Toplevel(parent)
    win.title(f'Bulk Purchasing & Pricing — {p["sku"]}')
    win.transient(parent)
    screen_w=win.winfo_screenwidth();screen_h=win.winfo_screenheight()
    win.geometry(f'{min(880,max(600,screen_w-90))}x{min(650,max(420,screen_h-110))}')
    win.minsize(min(610,screen_w-80),min(420,screen_h-95))
    frame=ttk.Frame(win,padding=(16,12));frame.pack(fill='both',expand=True)
    frame.columnconfigure(0,weight=1);frame.rowconfigure(2,weight=1)
    ttk.Label(frame,text=f'{p["name"]}  •  {p["sku"]}',style='Section.TLabel').grid(row=0,column=0,sticky='w')
    margin=margin_info(p['price'],p['cost'])
    margin_text='—' if margin['margin_percent'] is None else f'{margin["margin_percent"]:.1f}%'
    summary=tk.StringVar(value=f'Quoted item cost {money(p["cost"])}   •   Selling price {money(p["price"])}   •   Gross margin {margin_text}   •   Inventory basis {money(p["inventory_unit_cost"] if p["inventory_unit_cost"] is not None else p["cost"])}')
    ttk.Label(frame,textvariable=summary,wraplength=800).grid(row=1,column=0,sticky='w',pady=(5,11))
    book=ttk.Notebook(frame);book.grid(row=2,column=0,sticky='nsew')
    quote_tab=ttk.Frame(book,padding=18);tier_tab=ttk.Frame(book,padding=18);history_tab=ttk.Frame(book,padding=12)
    book.add(quote_tab,text='Bulk reorder cost');book.add(tier_tab,text='Supplier quantity tiers');book.add(history_tab,text='Cost history')
    quote_tab.columnconfigure(1,weight=1)
    qty=tk.StringVar(value=str(p['reorder_qty']))
    total=tk.StringVar(value=(f'{p["reorder_cost_total"]/100:.2f}' if p['reorder_cost_total'] is not None else ''))
    pack=tk.StringVar(value=str(p['case_pack_qty']))
    minimum=tk.StringVar(value=str(p['min_order_qty']))
    inputs=[('Reorder quantity (units)',qty),('Total bulk reorder cost ($)',total),
            ('Supplier case pack (units)',pack),('Supplier minimum order (units)',minimum)]
    for i,(name,var) in enumerate(inputs):
        ttk.Label(quote_tab,text=name).grid(row=i,column=0,sticky='w',padx=(0,15),pady=10)
        ttk.Entry(quote_tab,textvariable=var).grid(row=i,column=1,sticky='ew',pady=10)
    computed=tk.StringVar(value='—')
    ttk.Label(quote_tab,text='Calculated item cost',font=('Segoe UI',11,'bold')).grid(row=4,column=0,sticky='w',pady=(16,5))
    ttk.Label(quote_tab,textvariable=computed,font=('Segoe UI',17,'bold')).grid(row=4,column=1,sticky='w',pady=(16,5))
    ttk.Label(quote_tab,text='The bulk quote sets the item Cost column and suggests PO pricing. '
              'It does not reprice already-received inventory or rewrite invoices. '
              'Supplier tier pricing can override the suggested unit cost at larger quantities.',
              wraplength=600).grid(row=5,column=0,columnspan=2,sticky='w',pady=(10,12))
    def preview(*_):
        try:
            q=int(qty.get())
            val=cents(total.get())
            computed.set(money(rounded_cents(val,q)))
        except (ValueError,OverflowError):computed.set('Enter a valid quantity and total')
    qty.trace_add('write',preview);total.trace_add('write',preview)
    preview()
    def update_summary():
        row=db.execute('SELECT price,cost,inventory_unit_cost FROM products WHERE id=?',(product_id,)).fetchone()
        info=margin_info(row['price'],row['cost'])
        percent='—' if info['margin_percent'] is None else f'{info["margin_percent"]:.1f}%'
        basis=row['inventory_unit_cost'] if row['inventory_unit_cost'] is not None else row['cost']
        summary.set(f'Quoted item cost {money(row["cost"])}   •   Selling price {money(row["price"])}   •   Gross margin {percent}   •   Inventory basis {money(basis)}')
    def save_bulk():
        try:
            if not all(s.get().strip().isdecimal() for s in (qty,pack,minimum)):
                raise ValueError('Quantity, case pack and minimum must be positive whole numbers.')
            if total.get().strip():
                cost=set_bulk_quote(db,product_id,int(qty.get()),cents(total.get()),int(pack.get()),int(minimum.get()),actor)
            else:
                update_pack_rules(db,product_id,int(pack.get()),int(minimum.get()),actor)
                cost=db.execute('SELECT cost FROM products WHERE id=?',(product_id,)).fetchone()[0]
        except ValueError as e:
            messagebox.showerror('Bulk reorder pricing',str(e),parent=win);return
        update_summary();refresh_history()
        if on_saved:on_saved()
        messagebox.showinfo('Purchase settings saved',
                            f'Item cost is {money(cost)} per unit. Existing journal entries were not changed.',parent=win)
    ttk.Label(quote_tab,text='Use Save Bulk Quote & Pack Rules in the fixed footer below.',wraplength=600).grid(row=6,column=0,columnspan=2,sticky='w',pady=(5,0))
    ttk.Label(tier_tab,text='Quantity tiers override the base cost when ordering that many units or more.',
              wraplength=700).pack(anchor='w',pady=(0,9))
    tiers=ttk.Treeview(tier_tab,columns=('minimum','cost'),show='headings',height=8)
    tiers.heading('minimum',text='Minimum quantity');tiers.heading('cost',text='Unit cost')
    tiers.column('minimum',width=145,anchor='e');tiers.column('cost',width=165,anchor='e')
    tiers.pack(fill='both',expand=True)
    tier_controls=ttk.Frame(tier_tab);tier_controls.pack(fill='x',pady=(8,0))
    tier_qty=tk.StringVar();tier_cost=tk.StringVar()
    ttk.Label(tier_controls,text='From qty').grid(row=0,column=0,sticky='w')
    ttk.Entry(tier_controls,textvariable=tier_qty,width=11).grid(row=1,column=0,padx=(0,12))
    ttk.Label(tier_controls,text='Unit cost ($)').grid(row=0,column=1,sticky='w')
    ttk.Entry(tier_controls,textvariable=tier_cost,width=14).grid(row=1,column=1,padx=(0,12))
    def refresh_tiers():
        tiers.delete(*tiers.get_children())
        for row in price_tiers(db,product_id):
            tiers.insert('','end',iid=str(row['min_qty']),values=(row['min_qty'],money(row['unit_cost'])))
    def add_tier():
        try:
            if not tier_qty.get().strip().isdecimal():raise ValueError('Enter a positive minimum quantity.')
            set_price_tier(db,product_id,int(tier_qty.get()),cents(tier_cost.get()),actor)
        except ValueError as e:
            messagebox.showerror('Supplier pricing',str(e),parent=win);return
        refresh_tiers();refresh_history()
        if on_saved:on_saved()
    def remove_tier():
        ids=tiers.selection()
        if not ids:return
        delete_price_tier(db,product_id,int(ids[0]),actor)
        refresh_tiers();refresh_history()
        if on_saved:on_saved()
    ttk.Button(tier_controls,text='Save tier',command=add_tier).grid(row=1,column=2,padx=(0,8))
    ttk.Button(tier_controls,text='Remove selected tier',command=remove_tier).grid(row=1,column=3)
    def choose_tier(event=None):
        ids=tiers.selection()
        if ids:
            tier_qty.set(ids[0]);tier_cost.set(tiers.item(ids[0],'values')[1].replace('$','').replace(',',''))
    tiers.bind('<<TreeviewSelect>>',choose_tier)
    refresh_tiers()
    history=ttk.Treeview(history_tab,columns=('date','type','previous','current','bulk','note'),show='headings')
    for col,width in [('date',155),('type',120),('previous',110),('current',110),('bulk',110),('note',260)]:
        history.heading(col,text=col.title());history.column(col,width=width,stretch=False)
    history.pack(fill='both',expand=True)
    hscroll=ttk.Scrollbar(history_tab,orient='horizontal',command=history.xview)
    hscroll.pack(fill='x');history.configure(xscrollcommand=hscroll.set)
    def refresh_history():
        history.delete(*history.get_children())
        for r in cost_history(db,product_id):
            history.insert('','end',values=(r['changed_at'],r['change_type'],money(r['prior_cost']),
                money(r['new_cost']),('—' if r['new_bulk_total'] is None else money(r['new_bulk_total'])),
                r['note']))
    refresh_history()
    footer=ttk.Frame(frame);footer.grid(row=3,column=0,sticky='e',pady=(12,0))
    ttk.Button(footer,text='Close',command=win.destroy).pack(side='right')
    ttk.Button(footer,text='Save Bulk Quote & Pack Rules',command=save_bulk,style='Accent.TButton').pack(side='right',padx=(0,12))
    win.grab_set()
    return win
