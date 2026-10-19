"""TDZIGNS LLC BusinessDesk 2.0 — Windows/offline desktop business manager.
The local application uses the v1 core and extends it with v2 business workflows.
"""
import csv, hashlib, json, os, shutil, sqlite3, sys, tempfile, threading, urllib.request, webbrowser, subprocess, zipfile, re, uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from core_v1 import App as BaseApp, DB, DATA, cents, money
from sales_workflow import convert_estimate, record_invoice_payment
from supplier_catalog import supplier_choices, products_for_supplier, create_supplier_po, validate_supplier_rows
from update_support import read_status, signal_ready, STATUS_NAME
from install_location import choose_install_target, is_temporary_install
from release_layout import valid_release_names, inspect_release
from installer_assets import select_update_asset, validate_setup_file
from document_templates import render_document
from template_editor import open_template_editor
from visual_templates import load as load_visual_template, render as render_visual_document
from visual_template_editor import open_visual_template_editor
from modern_theme import apply as apply_modern_theme

VERSION = '2.9.9'
BUSINESS = 'TDZIGNS LLC'
RELEASE_MANIFEST_URL = 'https://github.com/combatengineer88/BusinessDesk/releases/latest/download/update_manifest.json'
TRUSTED_RELEASE_PREFIX = 'https://github.com/combatengineer88/BusinessDesk/releases/download/'
MEDIA = DATA / 'product_images'
MEDIA.mkdir(exist_ok=True)


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT, address TEXT);
    CREATE TABLE IF NOT EXISTS purchase_orders(id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
        ordered_on TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', notes TEXT DEFAULT '', total INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS po_items(id INTEGER PRIMARY KEY, po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
        product_id INTEGER NOT NULL REFERENCES products(id), qty INTEGER NOT NULL CHECK(qty>0),
        unit_cost INTEGER NOT NULL CHECK(unit_cost>=0));
    CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY, posted_on TEXT NOT NULL, memo TEXT NOT NULL,
        source_type TEXT NOT NULL, source_id INTEGER NOT NULL, UNIQUE(source_type,source_id));
    CREATE TABLE IF NOT EXISTS journal_lines(id INTEGER PRIMARY KEY, journal_id INTEGER NOT NULL REFERENCES journal(id),
        account TEXT NOT NULL, debit INTEGER NOT NULL DEFAULT 0, credit INTEGER NOT NULL DEFAULT 0,
        CHECK(debit>=0 AND credit>=0));
    CREATE TABLE IF NOT EXISTS update_settings(id INTEGER PRIMARY KEY CHECK(id=1), manifest_url TEXT DEFAULT '',
        check_at_launch INTEGER NOT NULL DEFAULT 0);
    INSERT OR IGNORE INTO update_settings(id,manifest_url,check_at_launch) VALUES(1,'',0);
    INSERT OR IGNORE INTO settings(key,value) VALUES('business_name','TDZIGNS LLC');
    INSERT OR IGNORE INTO settings(key,value) VALUES('business_address','');
    INSERT OR IGNORE INTO settings(key,value) VALUES('business_phone','');
    INSERT OR IGNORE INTO settings(key,value) VALUES('business_email','');
    INSERT OR IGNORE INTO settings(key,value) VALUES('logo_path','');
    ''')
    cols={r[1] for r in db.execute('PRAGMA table_info(products)')}
    if 'image_path' not in cols: db.execute('ALTER TABLE products ADD COLUMN image_path TEXT DEFAULT \'\'')
    if 'barcode' not in cols: db.execute('ALTER TABLE products ADD COLUMN barcode TEXT DEFAULT \'\'')
    columns={r[1] for r in db.execute('PRAGMA table_info(customers)')}
    if 'tax_exempt' not in columns:
        db.execute('ALTER TABLE customers ADD COLUMN tax_exempt INTEGER NOT NULL DEFAULT 0 CHECK(tax_exempt IN (0,1))')
    db.execute("""CREATE TABLE IF NOT EXISTS customer_prices(
        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        price INTEGER NOT NULL CHECK(price>=0),
        PRIMARY KEY(customer_id,product_id))""")
    # A product may optionally have one primary supplier. Existing products remain unassigned.
    product_columns={r[1] for r in db.execute('PRAGMA table_info(products)')}
    if 'supplier_id' not in product_columns:
        db.execute('ALTER TABLE products ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL')
    db.execute('CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_product_barcode ON products(barcode) WHERE barcode IS NOT NULL AND barcode != \'\'')
    db.executescript("""
    CREATE TRIGGER IF NOT EXISTS trg_invoice_journal AFTER INSERT ON documents
    WHEN NEW.kind='Invoice' BEGIN
      INSERT INTO journal(posted_on,memo,source_type,source_id)
      VALUES(NEW.created,'Invoice #'||NEW.id,'invoice',NEW.id);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES(last_insert_rowid(),'Accounts Receivable',NEW.total,0);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES((SELECT id FROM journal WHERE source_type='invoice' AND source_id=NEW.id),'Sales Revenue',0,NEW.subtotal);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      SELECT id,'Sales Tax Payable',0,NEW.tax FROM journal
      WHERE source_type='invoice' AND source_id=NEW.id AND NEW.tax>0;
    END;
    CREATE TRIGGER IF NOT EXISTS trg_invoice_cost AFTER INSERT ON document_items
    WHEN (SELECT kind FROM documents WHERE id=NEW.document_id)='Invoice'
    AND NEW.product_id IS NOT NULL BEGIN
      INSERT INTO journal(posted_on,memo,source_type,source_id)
      VALUES((SELECT created FROM documents WHERE id=NEW.document_id),
      'Cost of goods for invoice item #'||NEW.id,'cogs',NEW.id);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      SELECT last_insert_rowid(),'Cost of Goods Sold',NEW.qty*cost,0 FROM products WHERE id=NEW.product_id;
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      SELECT (SELECT id FROM journal WHERE source_type='cogs' AND source_id=NEW.id),
      'Inventory',0,NEW.qty*cost FROM products WHERE id=NEW.product_id;
    END;
    CREATE TRIGGER IF NOT EXISTS trg_payment_journal AFTER INSERT ON payments BEGIN
      INSERT INTO journal(posted_on,memo,source_type,source_id)
      VALUES(NEW.paid_on,'Payment for invoice #'||NEW.document_id,'payment',NEW.id);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES(last_insert_rowid(),'Cash',NEW.amount,0);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES((SELECT id FROM journal WHERE source_type='payment' AND source_id=NEW.id),
      'Accounts Receivable',0,NEW.amount);
    END;
    CREATE TRIGGER IF NOT EXISTS trg_expense_journal AFTER INSERT ON expenses BEGIN
      INSERT INTO journal(posted_on,memo,source_type,source_id)
      VALUES(NEW.spent_on,'Expense: '||NEW.category,'expense',NEW.id);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES(last_insert_rowid(),'Expense: '||NEW.category,NEW.amount,0);
      INSERT INTO journal_lines(journal_id,account,debit,credit)
      VALUES((SELECT id FROM journal WHERE source_type='expense' AND source_id=NEW.id),'Cash',0,NEW.amount);
    END;
    """)
    db.commit()


def post_journal(db, date, memo, source_type, source_id, entries):
    """Entries: [(account, debit_cents, credit_cents)]; rejects unbalanced postings."""
    entries=[(a,int(d),int(c)) for a,d,c in entries if d or c]
    if not entries or sum(d for _,d,_ in entries)!=sum(c for _,_,c in entries):
        raise ValueError('Journal entries must balance.')
    if any(d<0 or c<0 or (d and c) for _,d,c in entries): raise ValueError('Invalid journal lines.')
    cur=db.execute('INSERT INTO journal(posted_on,memo,source_type,source_id) VALUES(?,?,?,?)',
                   (date,memo,source_type,source_id))
    db.executemany('INSERT INTO journal_lines(journal_id,account,debit,credit) VALUES(?,?,?,?)',
                   [(cur.lastrowid,a,d,c) for a,d,c in entries])


def make_pdf(db, kind, record_id, output):
    """Export using the matching, saved document design (with safe defaults)."""
    if load_visual_template(db,kind) is not None:
        return render_visual_document(db,kind,record_id,output)
    return render_document(db,kind,record_id,output)


class BusinessDesk(BaseApp):
    def __init__(self):
        super().__init__()
        apply_modern_theme(self.root)
        self.root.geometry('1350x840')
        self.root.title(f'{BUSINESS} | BusinessDesk {VERSION}')
        # Health acknowledgement to the external updater once the login window is visible.
        self.root.after(400, lambda:signal_ready(DATA, VERSION, Path(sys.executable).resolve()))
    def login(self):
        schema(self.db)
        self._update_checked=False
        super().login()
    def setting(self,key):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else ''
    def home(self):
        super().home()
        # Compact captions keep all navigation tabs visible, while retaining stored order.
        tab_names={'Products / Catalog':'Products','Estimates & Invoices':'Estimates / Invoices',
                   'Administration':'Admin'}
        for tab in self.tabs.tabs():
            caption=self.tabs.tab(tab,'text')
            if caption in tab_names:self.tabs.tab(tab,text=tab_names[caption])
        # Replace plain application header with a consistent brand/navigation bar.
        header=self.root.winfo_children()[0]
        for child in header.winfo_children():child.destroy()
        header.configure(style='Header.TFrame',padding=(22,15))
        ttk.Label(header,text='◼  BUSINESSDESK',style='HeaderTitle.TLabel').pack(side='left',padx=(0,22))
        ttk.Label(header,text='TDZIGNS LLC  /  Business management',style='HeaderInfo.TLabel').pack(side='left')
        ttk.Label(header,text=f"{self.user['username']}   •   {self.user['role'].title()}   |   v{VERSION}",
                  style='HeaderInfo.TLabel').pack(side='right')
        self.tabs.bind('<<NotebookTabChanged>>',self._on_tab_changed)
        self.root.title(f'{BUSINESS} | BusinessDesk {VERSION}')
        for label,fn in [('Purchase Orders',self.purchase_orders),('Accounting',self.accounting),('Settings / Updates',self.settings_tab)]:
            frame=ttk.Frame(self.tabs,padding=12);self.tabs.add(frame,text=label);fn(frame)
        self._restore_tab_order()
        self.tabs.bind('<ButtonPress-1>',self._tab_drag_start,add='+')
        self.tabs.bind('<ButtonRelease-1>',self._tab_drag_end,add='+')
        if not getattr(self,'_update_checked',False):
            self._update_checked=True
            cfg=self.db.execute('SELECT manifest_url,check_at_launch FROM update_settings WHERE id=1').fetchone()
            if cfg and cfg['check_at_launch']:
                self.root.after(600,lambda url=(cfg['manifest_url'] or RELEASE_MANIFEST_URL):self.check_updates(url))
    def _on_tab_changed(self,event):
        # Refresh dashboard when revisited; do not rebuild the whole notebook.
        selected=self.tabs.select()
        if selected and self.tabs.tab(selected,'text')=='Dashboard':
            frame=self.tabs.nametowidget(selected)
            for widget in frame.winfo_children():widget.destroy()
            self.dashboard(frame)
    def _restore_tab_order(self):
        row=self.db.execute("SELECT value FROM settings WHERE key='tab_order'").fetchone()
        if not row:return
        try:
            labels=json.loads(row[0])
            if not isinstance(labels,list):return
            aliases={'Products / Catalog':'Products','Estimates & Invoices':'Estimates / Invoices',
                     'Administration':'Admin','Suppliers / Purchase Orders':'Purchase Orders',
                     'Accounting Ledger':'Accounting','Updates / Branding':'Settings / Updates'}
            labels=[aliases.get(label,label) for label in labels]
            frames={self.tabs.tab(tab,'text'):tab for tab in self.tabs.tabs()}
            for index,label in enumerate(labels):
                if label in frames:self.tabs.insert(index,frames[label])
        except (ValueError,TypeError,tk.TclError):pass

    def _tab_drag_start(self,event):
        self._drag_tab=None
        try:
            if self.tabs.identify(event.x,event.y)=='label':
                self._drag_tab=self.tabs.index('@%d,%d'%(event.x,event.y))
        except tk.TclError:pass

    def _tab_drag_end(self,event):
        source=getattr(self,'_drag_tab',None)
        self._drag_tab=None
        if source is None:return
        try:
            destination=self.tabs.index('@%d,%d'%(event.x,event.y))
            if destination!=source:
                moving=self.tabs.tabs()[source]
                self.tabs.insert(destination,moving)
                order=[self.tabs.tab(tab,'text') for tab in self.tabs.tabs()]
                with self.db:
                    self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('tab_order',?)",
                                    (json.dumps(order),))
        except tk.TclError:pass

    def select_document_products(self,kind,customer_id=None):
        products=list(self.db.execute('''SELECT p.id,p.sku,p.name,p.price,p.qty,cp.price AS special_price
            FROM products p LEFT JOIN customer_prices cp ON cp.product_id=p.id AND cp.customer_id=?
            ORDER BY p.name,p.sku''',(customer_id if customer_id is not None else -1,)))
        if not products:raise ValueError('Add products to the catalog first.')
        win=tk.Toplevel(self.root);win.title('Select '+kind+' products');win.transient(self.root);win.grab_set();win.geometry('940x620')
        search=tk.StringVar();qty=tk.StringVar(value='1');unit=tk.StringVar()
        ttk.Label(win,text='Search name or SKU').pack(anchor='w',padx=12,pady=4)
        ttk.Entry(win,textvariable=search).pack(fill='x',padx=12)
        catalog=ttk.Treeview(win,columns=('SKU','Product','Catalog','Customer','Stock'),show='headings',height=10)
        for col,width in [('SKU',130),('Product',320),('Catalog',100),('Customer',105),('Stock',75)]:
            catalog.heading(col,text=col);catalog.column(col,width=width)
        catalog.pack(fill='both',expand=True,padx=12,pady=8)
        controls=ttk.Frame(win,padding=8);controls.pack(fill='x')
        ttk.Label(controls,text='Quantity').pack(side='left')
        ttk.Entry(controls,textvariable=qty,width=7).pack(side='left',padx=5)
        ttk.Label(controls,text='Unit price ($)').pack(side='left')
        ttk.Entry(controls,textvariable=unit,width=12).pack(side='left',padx=5)
        lines=ttk.Treeview(win,columns=('SKU','Product','Qty','Unit','Total'),show='headings',height=6)
        for col,width in [('SKU',125),('Product',325),('Qty',75),('Unit',100),('Total',100)]:
            lines.heading(col,text=col);lines.column(col,width=width)
        lines.pack(fill='both',expand=True,padx=12,pady=8)
        chosen=[];out={'items':None}
        def refresh(*_):
            term=search.get().strip().casefold();catalog.delete(*catalog.get_children())
            for item in products:
                if term in (item['sku']+' '+item['name']).casefold():
                    catalog.insert('','end',iid=str(item['id']),values=(item['sku'],item['name'],money(item['price']),money(item['special_price']) if item['special_price'] is not None else 'Catalog',item['qty']))
        def product_selected(_=None):
            if catalog.selection():
                item=next(x for x in products if x['id']==int(catalog.selection()[0]))
                amount=item['special_price'] if item['special_price'] is not None else item['price']
                unit.set(f'{amount/100:.2f}')
        def row_selected(_=None):
            if lines.selection():
                item=chosen[lines.index(lines.selection()[0])]
                qty.set(str(item[2]));unit.set(f'{item[3]/100:.2f}')
        def numbers():
            count=int(qty.get());value=cents(unit.get())
            if count<=0:raise ValueError('Quantity must be positive.')
            return count,value
        def available(pid,quantity,exclude=None):
            if kind!='Invoice':return True
            item=next(x for x in products if x['id']==pid)
            reserved=sum(x[2] for i,x in enumerate(chosen) if x[0]==pid and i!=exclude)
            return reserved+quantity<=item['qty']
        def add():
            if not catalog.selection():return
            try: count,price=numbers()
            except ValueError as exc:messagebox.showerror('Invalid quantity or price',str(exc),parent=win);return
            item=next(x for x in products if x['id']==int(catalog.selection()[0]))
            if not available(item['id'],count):
                messagebox.showerror('Stock','Not enough stock.',parent=win);return
            chosen.append((item['id'],item['name'],count,price,count*price))
            lines.insert('','end',values=(item['sku'],item['name'],count,money(price),money(count*price)))
        def change():
            if not lines.selection():return
            index=lines.index(lines.selection()[0]);previous=chosen[index]
            try: count,price=numbers()
            except ValueError as exc:messagebox.showerror('Invalid line',str(exc),parent=win);return
            if not available(previous[0],count,exclude=index):
                messagebox.showerror('Stock','Not enough stock.',parent=win);return
            chosen[index]=(previous[0],previous[1],count,price,count*price)
            prod=next(x for x in products if x['id']==previous[0])
            lines.item(lines.selection()[0],values=(prod['sku'],previous[1],count,money(price),money(count*price)))
        def remove():
            for index in sorted((lines.index(x) for x in lines.selection()),reverse=True):
                chosen.pop(index);lines.delete(lines.get_children()[index])
        def done():
            if not chosen:messagebox.showwarning('Products','Select at least one product.',parent=win);return
            out['items']=list(chosen);win.destroy()
        search.trace_add('write',refresh);refresh()
        catalog.bind('<<TreeviewSelect>>',product_selected)
        catalog.bind('<Double-1>',lambda _:add())
        lines.bind('<<TreeviewSelect>>',row_selected)
        ttk.Button(controls,text='Add product',command=add).pack(side='left',padx=5)
        ttk.Button(controls,text='Update selected line',command=change).pack(side='left',padx=5)
        ttk.Button(controls,text='Remove line',command=remove).pack(side='left',padx=5)
        actions=ttk.Frame(win,padding=10);actions.pack(fill='x')
        ttk.Button(actions,text='Cancel',command=win.destroy).pack(side='right',padx=5)
        ttk.Button(actions,text='Save line items',command=done).pack(side='right',padx=5)
        win.wait_window();return out['items']

    def dashboard(self,p):
        invoices=self.db.execute("SELECT count(*),coalesce(sum(total),0) FROM documents WHERE kind='Invoice'").fetchone()
        estimates=self.db.execute("SELECT count(*),coalesce(sum(total),0) FROM documents WHERE kind='Estimate'").fetchone()
        received=self.db.execute('SELECT coalesce(sum(amount),0) FROM payments').fetchone()[0]
        expenses=self.db.execute('SELECT coalesce(sum(amount),0) FROM expenses').fetchone()[0]
        products=self.db.execute('SELECT count(*) FROM products').fetchone()[0]
        customers=self.db.execute('SELECT count(*) FROM customers').fetchone()[0]
        ttk.Label(p,text='Overview',style='Section.TLabel').pack(anchor='w',pady=(8,4))
        ttk.Label(p,text='Key business figures at a glance. Select a tab above to manage records.',
                  foreground='#64748B').pack(anchor='w',pady=(0,20))
        stats=[('Invoiced',money(invoices[1]),f'{invoices[0]} invoices'),
               ('Payments received',money(received),'Recorded invoice payments'),
               ('Outstanding balance',money(invoices[1]-received),'Invoiced amount less payments'),
               ('Recorded expenses',money(expenses),'Business expense entries'),
               ('Estimates',money(estimates[1]),f'{estimates[0]} estimates • not revenue'),
               ('Catalog products',str(products),'Inventory and available services'),
               ('Customers',str(customers),'Saved customer records')]
        grid=ttk.Frame(p);grid.pack(fill='both',expand=False)
        for i,(name,value,caption) in enumerate(stats):
            r,c=divmod(i,3)
            card=ttk.Frame(grid,style='Card.TFrame',padding=(17,16))
            card.grid(row=r,column=c,sticky='nsew',padx=7,pady=8)
            ttk.Label(card,text=name,style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(card,text=value,style='CardValue.TLabel').pack(anchor='w',pady=(9,7))
            ttk.Label(card,text=caption,style='CardCaption.TLabel',wraplength=265).pack(anchor='w')
        for col in range(3):grid.columnconfigure(col,weight=1,uniform='dashboard')
        ttk.Label(p,text='Financial figures are operational summaries, not a complete accounting ledger or tax report.',
                  foreground='#64748B').pack(anchor='w',pady=(16,7))
        ttk.Button(p,text='Refresh overview',style='Accent.TButton',command=self.home).pack(anchor='w',pady=(2,10))

    def customers(self,p):
        bar=ttk.Frame(p);bar.pack(fill='x')
        tree=self.table(p,('ID','Name','Email','Phone','Address','Tax-exempt','Notes'))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute('SELECT * FROM customers ORDER BY name'):
                tree.insert('','end',values=(r['id'],r['name'],r['email'] or '',r['phone'] or '',
                    r['address'] or '','Yes' if r['tax_exempt'] else 'No',r['notes'] or ''))
        def edit(new=False):
            cid=None if new else self.selected(tree)
            record={} if new else dict(self.db.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone())
            win=tk.Toplevel(self.root);win.title('Customer');win.transient(self.root);win.grab_set()
            fields={}
            for index,key in enumerate(('name','email','phone','address','notes')):
                ttk.Label(win,text=key.title()).grid(row=index,column=0,padx=12,pady=7,sticky='w')
                variable=tk.StringVar(value=str(record.get(key) or ''))
                ttk.Entry(win,textvariable=variable,width=43).grid(row=index,column=1,padx=12,pady=7)
                fields[key]=variable
            tax_exempt=tk.BooleanVar(value=bool(record.get('tax_exempt',0)))
            ttk.Checkbutton(win,text='Tax-exempt customer',variable=tax_exempt).grid(row=5,column=0,columnspan=2,pady=5)
            ttk.Label(win,text='Verify a valid exemption certificate and applicable tax rules.').grid(row=6,column=0,columnspan=2,pady=5)
            def save():
                vals=[fields[k].get().strip() for k in ('name','email','phone','address','notes')]
                if not vals[0]:
                    messagebox.showerror('Customer','Name is required.',parent=win);return
                with self.db:
                    if new:self.db.execute('INSERT INTO customers(name,email,phone,address,notes,tax_exempt) VALUES(?,?,?,?,?,?)',(*vals,int(tax_exempt.get())))
                    else:self.db.execute('UPDATE customers SET name=?,email=?,phone=?,address=?,notes=?,tax_exempt=? WHERE id=?',(*vals,int(tax_exempt.get()),cid))
                win.destroy();refresh()
            ttk.Button(win,text='Save',command=save).grid(row=7,column=1,pady=12,sticky='e')
            ttk.Button(win,text='Cancel',command=win.destroy).grid(row=7,column=0,pady=12)
            win.wait_window()
        self.button(bar,'Add customer',lambda:edit(True))
        self.button(bar,'Edit selected',edit)
        self.button(bar,'Customer product prices',lambda:self.customer_price_manager(self.selected(tree)))
        self.button(bar,'Import customers from Excel',lambda:self.import_excel_dialog('customers'))
        refresh()

    def customer_price_manager(self,customer_id):
        customer=self.db.execute('SELECT name FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not customer:raise ValueError('Customer not found.')
        products=list(self.db.execute('SELECT id,sku,name,price FROM products ORDER BY name'))
        if not products:raise ValueError('Add products to the catalog first.')
        win=tk.Toplevel(self.root);win.title('Special prices — '+customer['name'])
        win.transient(self.root);win.grab_set();win.geometry('750x500')
        ttk.Label(win,text='Customer-specific prices for '+customer['name'],font=('Segoe UI',13,'bold')).pack(padx=12,pady=10,anchor='w')
        ttk.Label(win,text='These apply to new estimates/invoices; existing documents are unchanged.').pack(padx=12,anchor='w')
        table=ttk.Treeview(win,columns=('SKU','Product','Catalog','Special'),show='headings')
        for col,width in [('SKU',110),('Product',310),('Catalog',110),('Special',110)]:
            table.heading(col,text=col);table.column(col,width=width)
        table.pack(fill='both',expand=True,padx=12,pady=12)
        def refresh():
            table.delete(*table.get_children())
            special={r['product_id']:r['price'] for r in self.db.execute('SELECT product_id,price FROM customer_prices WHERE customer_id=?',(customer_id,))}
            for prod in products:
                table.insert('','end',iid=str(prod['id']),values=(prod['sku'],prod['name'],money(prod['price']),money(special[prod['id']]) if prod['id'] in special else 'Catalog'))
        price=tk.StringVar();bottom=ttk.Frame(win,padding=10);bottom.pack(fill='x')
        ttk.Label(bottom,text='Price ($)').pack(side='left')
        ttk.Entry(bottom,textvariable=price,width=12).pack(side='left',padx=8)
        def selected_product():
            selection=table.selection()
            if not selection:raise ValueError('Select a product first.')
            return int(selection[0])
        def save():
            pid=selected_product();value=cents(price.get())
            with self.db:self.db.execute('INSERT INTO customer_prices(customer_id,product_id,price) VALUES(?,?,?) ON CONFLICT(customer_id,product_id) DO UPDATE SET price=excluded.price',(customer_id,pid,value))
            refresh()
        def reset():
            pid=selected_product()
            with self.db:self.db.execute('DELETE FROM customer_prices WHERE customer_id=? AND product_id=?',(customer_id,pid))
            price.set('');refresh()
        def choose(_):
            if table.selection():
                result=self.db.execute('SELECT price FROM customer_prices WHERE customer_id=? AND product_id=?',(customer_id,int(table.selection()[0]))).fetchone()
                price.set(f'{result[0]/100:.2f}' if result else '')
        table.bind('<<TreeviewSelect>>',choose)
        ttk.Button(bottom,text='Save price',command=lambda:self._safe(save)).pack(side='left',padx=6)
        ttk.Button(bottom,text='Use catalog price',command=lambda:self._safe(reset)).pack(side='left',padx=6)
        ttk.Button(bottom,text='Close',command=win.destroy).pack(side='right')
        refresh();win.wait_window()

    def _safe(self,fn):
        try:fn()
        except Exception as exc:self.error(exc)

    def document_header_dialog(self,customers):
        win=tk.Toplevel(self.root);win.title('New estimate or invoice');win.transient(self.root);win.grab_set()
        win.resizable(False,False)
        labels=[f"{c['name']} (ID {c['id']})" for c in customers]
        chosen=tk.StringVar(value=labels[0]);kind=tk.StringVar(value='Estimate')
        rate=tk.StringVar(value=self.setting('default_tax_rate') or '0');notes=tk.StringVar()
        for index,label in enumerate(('Customer','Type','Tax rate (%)','Notes')):
            ttk.Label(win,text=label).grid(row=index,column=0,padx=12,pady=8,sticky='w')
        ttk.Combobox(win,values=labels,textvariable=chosen,state='readonly',width=42).grid(row=0,column=1,pady=8)
        ttk.Combobox(win,values=['Estimate','Invoice'],textvariable=kind,state='readonly').grid(row=1,column=1,sticky='w')
        rate_entry=ttk.Entry(win,textvariable=rate,width=14);rate_entry.grid(row=2,column=1,sticky='w')
        ttk.Entry(win,textvariable=notes,width=44).grid(row=3,column=1,pady=8)
        status=ttk.Label(win,text='');status.grid(row=4,column=0,columnspan=2,pady=5)
        def is_exempt():
            cid=customers[labels.index(chosen.get())]['id']
            return bool(self.db.execute('SELECT tax_exempt FROM customers WHERE id=?',(cid,)).fetchone()[0])
        def refresh(*_):
            exempt=is_exempt()
            rate_entry.configure(state='disabled' if exempt else 'normal')
            status.configure(text='Tax-exempt: sales tax will be $0.00' if exempt else 'Taxable customer')
        chosen.trace_add('write',refresh);refresh()
        result={'value':None}
        def done():
            cid=customers[labels.index(chosen.get())]['id']
            result['value']={'customer':str(cid),'kind':kind.get(),'tax':'0' if is_exempt() else rate.get(),'notes':notes.get()}
            win.destroy()
        ttk.Button(win,text='Continue to products',command=done).grid(row=5,column=1,sticky='e',padx=12,pady=12)
        ttk.Button(win,text='Cancel',command=win.destroy).grid(row=5,column=0,sticky='w',padx=12)
        win.wait_window();return result['value']

    def import_excel_dialog(self,kind):
        from excel_import import read_excel,import_rows
        if self.user['role']!='admin':
            raise PermissionError('Administrator login required to import business records.')
        path=filedialog.askopenfilename(title='Choose Excel '+kind+' file',
            filetypes=[('Excel workbooks','*.xlsx *.xlsm')])
        if not path:return
        rows,errors,sheet=read_excel(path,kind)
        if not rows and not errors:raise ValueError('No records found in the selected worksheet.')
        preview='\n'.join(
            f"Row {n}: {v.get('sku','')} {v['name']}" for n,v in rows[:8])
        problem='\n'.join(f'Row {n}: {reason}' for n,reason in errors[:8])
        if errors:
            messagebox.showerror('Import validation failed',
                f'{len(errors)} invalid row(s). No records were imported.\n\n{problem}')
            return
        if not rows:raise ValueError('No valid rows found.')
        if kind=='products':
            # Reject unknown/ambiguous suppliers before any changes or confirmation.
            validate_supplier_rows(self.db,rows)
        choice=messagebox.askyesnocancel('Import '+kind,
            f'Worksheet: {sheet}\nValid records: {len(rows)}\n\n{preview}\n\n'
            'Duplicate handling:\nYES = update matching records\n'
            'NO = skip matching records\nCANCEL = do not import.\n\n'
            'Products match by SKU; customers and suppliers match by name. '
            'Updating product quantities REPLACES current stock counts. '
            'The optional Supplier column must match a saved supplier name.')
        if choice is None:return
        mode='update' if choice else 'skip'
        created,updated,skipped=import_rows(self.db,kind,rows,mode)
        messagebox.showinfo('Import complete',
            f'Added: {created}\nUpdated: {updated}\nSkipped: {skipped}')
        self.home()

    def products(self,p):
        bar=ttk.Frame(p);bar.pack(fill='x')
        search=tk.StringVar()
        ttk.Label(bar,text='Search SKU / barcode / product:').pack(side='left',padx=3)
        ttk.Entry(bar,textvariable=search,width=26).pack(side='left',padx=4)
        tree=self.table(p,('ID','SKU','Barcode','Name','Supplier','Description','Price','Cost','Stock','Image'))
        def refresh(*_):
            tree.delete(*tree.get_children())
            term='%'+search.get().strip()+'%'
            sql="""SELECT p.*,s.name AS supplier_name FROM products p
                LEFT JOIN suppliers s ON s.id=p.supplier_id
                WHERE p.sku LIKE ? OR p.barcode LIKE ? OR p.name LIKE ? OR s.name LIKE ?
                ORDER BY p.name COLLATE NOCASE"""
            for r in self.db.execute(sql,(term,term,term,term)):
                tree.insert('','end',values=(r['id'],r['sku'],r['barcode'],r['name'],
                     r['supplier_name'] or 'Unassigned',r['description'],money(r['price']),
                     money(r['cost']),r['qty'],'Yes' if r['image_path'] else ''))
        search.trace_add('write',refresh)
        def edit(new=False):
            product_id=None if new else self.selected(tree)
            record={} if new else dict(self.db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone())
            if not new and not record:raise ValueError('Product no longer exists.')
            dialog=tk.Toplevel(self.root)
            dialog.title('Add product' if new else 'Edit product')
            dialog.transient(self.root);dialog.grab_set();dialog.resizable(False,False)
            fields={}
            for i,key in enumerate(('sku','barcode','name','description','price','cost','qty')):
                ttk.Label(dialog,text=key.replace('_',' ').title()).grid(row=i,column=0,padx=12,pady=7,sticky='w')
                initial=(f"{record.get(key,0)/100:.2f}" if key in ('price','cost') and record else
                         str(record.get(key) if record.get(key) is not None else ('0' if key in ('price','cost','qty') else '')))
                value=tk.StringVar(value=initial)
                ttk.Entry(dialog,textvariable=value,width=42).grid(row=i,column=1,padx=12,pady=7)
                fields[key]=value
            options=supplier_choices(self.db)
            labels=['Unassigned']+[f"{x['name']} (#{x['id']})" for x in options]
            initial_supplier=record.get('supplier_id')
            supplier_index=next((i for i,x in enumerate(options,1) if x['id']==initial_supplier),0)
            ttk.Label(dialog,text='Primary supplier').grid(row=7,column=0,padx=12,pady=7,sticky='w')
            supplier=ttk.Combobox(dialog,values=labels,state='readonly',width=39)
            supplier.grid(row=7,column=1,padx=12,pady=7)
            supplier.current(supplier_index)
            ttk.Label(dialog,text='Only products assigned to a supplier appear in that supplier’s new POs.',
                      foreground='#555555').grid(row=8,column=0,columnspan=2,padx=12,pady=(0,8))
            def save():
                try:
                    vals={k:v.get().strip() for k,v in fields.items()}
                    if not vals['sku'] or not vals['name']:raise ValueError('SKU and name are required.')
                    quantity=int(vals['qty'])
                    if quantity<0:raise ValueError('Stock cannot be negative.')
                    unit_price=cents(vals['price']);cost=cents(vals['cost'])
                    sid=options[supplier.current()-1]['id'] if supplier.current()>0 else None
                    values=(vals['sku'],vals['barcode'],vals['name'],vals['description'],unit_price,cost,quantity,sid)
                    with self.db:
                        if new:
                            self.db.execute('''INSERT INTO products(sku,barcode,name,description,price,cost,qty,supplier_id)
                                               VALUES(?,?,?,?,?,?,?,?)''',values)
                        else:
                            self.db.execute('''UPDATE products SET sku=?,barcode=?,name=?,description=?,price=?,cost=?,qty=?,supplier_id=?
                                               WHERE id=?''',(*values,product_id))
                except (ValueError,sqlite3.IntegrityError) as exc:
                    messagebox.showerror('Product',str(exc),parent=dialog)
                    return
                dialog.destroy();refresh()
            ttk.Button(dialog,text='Save product',command=save).grid(row=9,column=1,sticky='e',padx=12,pady=12)
            ttk.Button(dialog,text='Cancel',command=dialog.destroy).grid(row=9,column=0,sticky='w',padx=12,pady=12)
            dialog.wait_window()
        def attach_image():
            id=self.selected(tree)
            path=filedialog.askopenfilename(filetypes=[('Image files','*.png *.jpg *.jpeg *.gif')])
            if not path:return
            ext=Path(path).suffix.lower()
            if ext not in ('.png','.jpg','.jpeg','.gif'):raise ValueError('Unsupported image format.')
            dest=MEDIA/f'product_{id}{ext}'
            shutil.copy2(path,dest)
            with self.db:self.db.execute('UPDATE products SET image_path=? WHERE id=?',(str(dest),id))
            refresh()
        def view_image():
            id=self.selected(tree)
            r=self.db.execute('SELECT image_path FROM products WHERE id=?',(id,)).fetchone()
            if not r['image_path'] or not Path(r['image_path']).exists():raise ValueError('No image assigned.')
            win=tk.Toplevel(self.root);win.title('Product image')
            try:
                from PIL import Image,ImageTk
                img=Image.open(r['image_path']);img.thumbnail((700,500));photo=ImageTk.PhotoImage(img)
            except ImportError:photo=tk.PhotoImage(file=r['image_path'])
            label=tk.Label(win,image=photo);label.image=photo;label.pack(padx=10,pady=10)
        self.button(bar,'Add product',lambda:edit(True));self.button(bar,'Edit',edit)
        self.button(bar,'Import products from Excel',lambda:self.import_excel_dialog('products'))
        self.button(bar,'Attach image',attach_image);self.button(bar,'View image',view_image)
        self.button(bar,'Export catalog CSV',lambda:self.export('''SELECT p.sku,p.barcode,p.name,p.description,
            p.price/100.0 AS price,p.cost/100.0 AS cost,p.qty,s.name AS supplier,p.image_path
            FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id'''))
        ttk.Label(p,text='Select a primary supplier to include a product in that supplier’s purchase orders.').pack(anchor='w')
        refresh()
    def documents(self,p):
        super().documents(p)
        # Replace legacy payment action with the improved invoice-specific flow.
        for container in p.winfo_children():
            for widget in container.winfo_children():
                if isinstance(widget,ttk.Button) and widget.cget('text')=='Record payment':widget.destroy()
        bar=ttk.Frame(p);bar.pack(fill='x')
        # core creates a table; locate it by traversing the tab
        def find_tree(widget):
            if isinstance(widget,ttk.Treeview):return widget
            for child in widget.winfo_children():
                result=find_tree(child)
                if result:return result
        tree=find_tree(p)
        def export_pdf():
            id=self.selected(tree)
            d=self.db.execute('SELECT kind FROM documents WHERE id=?',(id,)).fetchone()
            path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'{d["kind"]}_{id}.pdf',filetypes=[('PDF','*.pdf')])
            if path:make_pdf(self.db,d['kind'],id,path);messagebox.showinfo('Saved','Branded PDF exported.')
        def convert_selected():
            docid=self.selected(tree)
            kind=self.db.execute('SELECT kind FROM documents WHERE id=?',(docid,)).fetchone()['kind']
            if kind!='Estimate':raise ValueError('Select an Estimate row to convert.')
            if not messagebox.askyesno('Convert estimate',f'Convert estimate #{docid} into an invoice? Stock will be deducted.'):
                return
            convert_estimate(self.db,docid)
            messagebox.showinfo('Converted',f'Estimate #{docid} is now invoice #{docid}. Select it and record a payment.')
            self.home()
        def pay_selected():
            docid=self.selected(tree)
            doc=self.db.execute('SELECT kind,total FROM documents WHERE id=?',(docid,)).fetchone()
            if doc['kind']!='Invoice':raise ValueError('This is an estimate. Click Convert estimate to invoice first.')
            paid=self.db.execute('SELECT coalesce(sum(amount),0) FROM payments WHERE document_id=?',(docid,)).fetchone()[0]
            due=doc['total']-paid
            if due<=0:raise ValueError('Invoice already paid.')
            v=self.form('Record invoice payment',[('amount',f'Amount due: {money(due)}'),('method','Payment method')],
                        {'amount':f'{due/100:.2f}'})
            if not v:return
            record_invoice_payment(self.db,docid,cents(v['amount']),v['method'])
            messagebox.showinfo('Payment saved',f'Payment recorded for invoice #{docid}.')
            self.home()
        self.button(bar,'Convert estimate to invoice',convert_selected)
        self.button(bar,'Record invoice payment',pay_selected)
        self.button(bar,'Export selected branded PDF',export_pdf)
        if self.user['role']=='admin':self.button(bar,'Customize PDF templates',self.edit_document_templates)
    def select_po_supplier(self):
        """Pick a saved supplier by name; keep the numeric ID internal."""
        suppliers=list(self.db.execute('SELECT id,name FROM suppliers ORDER BY name COLLATE NOCASE,id'))
        if not suppliers:
            raise ValueError('No suppliers found. Add or import a supplier before creating a purchase order.')

        window=tk.Toplevel(self.root)
        window.title('New Purchase Order — Select Supplier')
        window.transient(self.root)
        window.resizable(False, False)
        window.grab_set()
        frame=ttk.Frame(window,padding=18)
        frame.pack(fill='both',expand=True)

        ttk.Label(frame,text='Supplier').grid(row=0,column=0,sticky='w',padx=(0,12),pady=8)
        # Display IDs only to distinguish suppliers that happen to share a name.
        labels=[f'{supplier["name"]} (#{supplier["id"]})' for supplier in suppliers]
        selection=ttk.Combobox(frame,values=labels,state='readonly',width=52)
        selection.grid(row=0,column=1,sticky='ew',pady=8)
        selection.set('')  # No accidental supplier selection.
        selection.focus_set()

        ttk.Label(frame,text='Notes').grid(row=1,column=0,sticky='nw',padx=(0,12),pady=8)
        notes=tk.Text(frame,width=52,height=5,wrap='word')
        notes.grid(row=1,column=1,sticky='ew',pady=8)
        result={'value':None}

        def confirm(event=None):
            index=selection.current()
            if index<0:
                messagebox.showwarning('Select a supplier',
                    'Choose a supplier from the dropdown before continuing.',parent=window)
                selection.focus_set()
                return
            supplier_id=suppliers[index]['id']
            # Re-check the record in case it was removed while this dialog was open.
            if not self.db.execute('SELECT 1 FROM suppliers WHERE id=?',(supplier_id,)).fetchone():
                messagebox.showerror('Supplier unavailable',
                    'This supplier no longer exists. Reopen the purchase order form.',parent=window)
                return
            result['value']={'supplier_id':supplier_id,'notes':notes.get('1.0','end-1c').strip()}
            window.destroy()

        buttons=ttk.Frame(frame)
        buttons.grid(row=2,column=1,sticky='e',pady=(12,0))
        ttk.Button(buttons,text='Cancel',command=window.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Continue',command=confirm).pack(side='right')
        selection.bind('<Return>',confirm)
        window.bind('<Escape>',lambda event:window.destroy())
        window.protocol('WM_DELETE_WINDOW',window.destroy)
        window.wait_window()
        return result['value']

    def select_po_products(self,supplier_id):
        """Choose PO items for one supplier without entering internal product IDs."""
        products=products_for_supplier(self.db,supplier_id)
        supplier_row=self.db.execute('SELECT name FROM suppliers WHERE id=?',(supplier_id,)).fetchone()
        supplier_name=supplier_row['name'] if supplier_row else 'selected supplier'
        if not products:
            messagebox.showinfo('No products for supplier',
                'No catalog products are assigned to this supplier.\n\n'
                'Open Products / Catalog, edit the products, and choose this supplier.\n'
                'You can also import product assignments using the Supplier Excel column.',
                parent=self.root)
            return None
        dialog=tk.Toplevel(self.root)
        dialog.title(f'New Purchase Order — {supplier_name}')
        dialog.transient(self.root);dialog.grab_set();dialog.geometry('780x510')
        top=ttk.Frame(dialog,padding=14);top.pack(fill='x')
        ttk.Label(top,text=f'Product supplied by {supplier_name}').grid(row=0,column=0,sticky='w')
        labels=[f"{p['sku']} — {p['name']}" for p in products]
        chosen=ttk.Combobox(top,values=labels,state='readonly',width=54)
        chosen.grid(row=1,column=0,columnspan=3,sticky='ew',pady=(4,14))
        ttk.Label(top,text='Quantity').grid(row=2,column=0,sticky='w')
        ttk.Label(top,text='Unit cost ($)').grid(row=2,column=1,sticky='w')
        quantity=tk.StringVar(value='1');cost=tk.StringVar()
        ttk.Entry(top,textvariable=quantity,width=12).grid(row=3,column=0,sticky='w',pady=5)
        ttk.Entry(top,textvariable=cost,width=16).grid(row=3,column=1,sticky='w',pady=5)
        def choice_changed(_=None):
            index=chosen.current()
            if index>=0:cost.set(f"{products[index]['cost']/100:.2f}")
        chosen.bind('<<ComboboxSelected>>',choice_changed)
        selected=[]
        table=ttk.Treeview(dialog,columns=('SKU','Product','Quantity','Unit cost','Line total'),show='headings',height=10)
        for title,width in [('SKU',115),('Product',265),('Quantity',75),('Unit cost',110),('Line total',110)]:
            table.heading(title,text=title);table.column(title,width=width)
        table.pack(fill='both',expand=True,padx=14,pady=(5,10))
        total_label=ttk.Label(dialog,text='Order total: $0.00',font=('Segoe UI',11,'bold'))
        total_label.pack(anchor='e',padx=16)
        def refresh_total():
            total_label.configure(text=f"Order total: {money(sum(q*c for _,q,c in selected))}")
        def add():
            index=chosen.current()
            if index<0:
                messagebox.showwarning('Choose product','Select a product from the dropdown.',parent=dialog);return
            product=products[index]
            try:
                qty=int(quantity.get())
                if qty<1:raise ValueError('Quantity must be at least 1.')
                unit_cost=cents(cost.get())
            except ValueError as exc:
                messagebox.showerror('Invalid PO line',str(exc),parent=dialog);return
            if any(pid==product['id'] for pid,_,_ in selected):
                messagebox.showwarning('Duplicate product','This product is already on the PO. Remove its line to change the quantity or cost.',parent=dialog)
                return
            selected.append((product['id'],qty,unit_cost))
            table.insert('','end',values=(product['sku'],product['name'],qty,money(unit_cost),money(qty*unit_cost)))
            refresh_total()
        def remove():
            for index in sorted((table.index(iid) for iid in table.selection()),reverse=True):
                selected.pop(index)
                table.delete(table.get_children()[index])
            refresh_total()
        bar=ttk.Frame(dialog,padding=10);bar.pack(fill='x')
        ttk.Button(top,text='Add to PO',command=add).grid(row=3,column=2,sticky='e',padx=14)
        ttk.Button(bar,text='Remove selected line',command=remove).pack(side='left')
        result={'items':None}
        def done():
            if not selected:
                messagebox.showwarning('Empty PO','Add at least one supplier product.',parent=dialog);return
            result['items']=list(selected);dialog.destroy()
        ttk.Button(bar,text='Cancel',command=dialog.destroy).pack(side='right',padx=5)
        ttk.Button(bar,text='Create purchase order',command=done).pack(side='right',padx=5)
        dialog.bind('<Escape>',lambda _:dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW',dialog.destroy)
        dialog.wait_window()
        return result['items']

    def purchase_orders(self,p):
        bar=ttk.Frame(p);bar.pack(fill='x')
        tree=self.table(p,('ID','Supplier','Ordered','Status','Total'))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute('SELECT p.*,s.name FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC'):
                tree.insert('','end',values=(r['id'],r['name'],r['ordered_on'],r['status'],money(r['total'])))
        self.button(bar,'Import suppliers from Excel',lambda:self.import_excel_dialog('suppliers'))
        def supplier():
            v=self.form('New supplier',[(x,x.title()) for x in ('name','email','phone','address')])
            if not v:return
            if not v['name']:raise ValueError('Supplier name required.')
            with self.db:self.db.execute('INSERT INTO suppliers(name,email,phone,address) VALUES(?,?,?,?)',tuple(v.values()))
            messagebox.showinfo('Supplier added','Supplier saved.')
        def create():
            selection=self.select_po_supplier()
            if not selection:return
            supplier_id=selection['supplier_id']
            items=self.select_po_products(supplier_id)
            if not items:return
            po_id=create_supplier_po(self.db,supplier_id,selection['notes'],items,
                                     datetime.now().strftime('%Y-%m-%d'))
            messagebox.showinfo('Purchase order created',f'Purchase order #{po_id} saved for the selected supplier.')
            refresh()
        def receive():
            id=self.selected(tree)
            row=self.db.execute('SELECT * FROM purchase_orders WHERE id=?',(id,)).fetchone()
            if row['status']!='Open':raise ValueError('This purchase order has already been received.')
            if not messagebox.askyesno('Receive stock','Receive all PO lines and record accounts payable?'):return
            with self.db:
                for x in self.db.execute('SELECT * FROM po_items WHERE po_id=?',(id,)).fetchall():
                    self.db.execute('UPDATE products SET qty=qty+? WHERE id=?',(x['qty'],x['product_id']))
                self.db.execute("UPDATE purchase_orders SET status='Received' WHERE id=?",(id,))
                if row['total']:
                    post_journal(self.db,datetime.now().strftime('%Y-%m-%d'),f'Purchase order #{id} received','po',id,
                                 [('Inventory',row['total'],0),('Accounts Payable',0,row['total'])])
            refresh()
        def pdf():
            id=self.selected(tree)
            path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'PO_{id}.pdf',filetypes=[('PDF','*.pdf')])
            if path:make_pdf(self.db,'PO',id,path);messagebox.showinfo('Saved','Purchase order PDF exported.')
        self.button(bar,'Add supplier',supplier);self.button(bar,'New PO',create)
        self.button(bar,'Receive entire PO',receive);self.button(bar,'Export PO PDF',pdf)
        if self.user['role']=='admin':self.button(bar,'Customize PO template',self.edit_document_templates)
        ttk.Label(p,text='Receiving a PO increases inventory and records an accounts payable liability. Partial receiving and vendor payment are not yet supported.').pack(anchor='w')
        refresh()
    def accounting(self,p):
        bar=ttk.Frame(p);bar.pack(fill='x')
        tree=self.table(p,('Date','Account','Debit','Credit','Memo','Source'))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute('SELECT j.posted_on,l.account,l.debit,l.credit,j.memo,j.source_type||" #"||j.source_id AS source FROM journal j JOIN journal_lines l ON l.journal_id=j.id ORDER BY j.id DESC,l.id'):
                tree.insert('','end',values=(r['posted_on'],r['account'],money(r['debit']),money(r['credit']),r['memo'],r['source']))
        def entry():
            if self.user['role']!='admin':raise ValueError('Only admins can create manual journal entries.')
            v=self.form('Manual journal entry',[('date','Date YYYY-MM-DD'),('memo','Memo'),('debit_account','Debit account'),('credit_account','Credit account'),('amount','Amount')],
                        {'date':datetime.now().strftime('%Y-%m-%d')})
            if not v:return
            datetime.strptime(v['date'],'%Y-%m-%d')
            if not v['memo'] or not v['debit_account'] or not v['credit_account'] or v['debit_account']==v['credit_account']:
                raise ValueError('Enter memo and two different accounts.')
            amount=cents(v['amount'])
            if amount<=0:raise ValueError('Amount must be positive.')
            with self.db:
                source_id=self.db.execute('SELECT coalesce(max(source_id),0)+1 FROM journal WHERE source_type="manual"').fetchone()[0]
                post_journal(self.db,v['date'],v['memo'],'manual',source_id,[(v['debit_account'],amount,0),(v['credit_account'],0,amount)])
            refresh()
        def balances():
            rows=list(self.db.execute('SELECT account,sum(debit)-sum(credit) AS balance FROM journal_lines GROUP BY account ORDER BY account'))
            win=tk.Toplevel(self.root);win.title('Account balances')
            txt=tk.Text(win,width=68,height=25);txt.pack(padx=10,pady=10)
            for r in rows:txt.insert('end',f'{r["account"]:<36}{money(abs(r["balance"]))} {"DR" if r["balance"]>=0 else "CR"}\n')
            txt.configure(state='disabled')
        self.button(bar,'Manual journal entry',entry);self.button(bar,'Account balances',balances)
        self.button(bar,'Export ledger CSV',lambda:self.export('SELECT j.posted_on,l.account,l.debit/100.0 AS debit,l.credit/100.0 AS credit,j.memo,j.source_type,j.source_id FROM journal j JOIN journal_lines l ON l.journal_id=j.id ORDER BY j.id,l.id'))
        ttk.Label(p,text='Journal includes v2 PO receipts, manual entries, and v2 transactions. Pre-existing v1 transactions are NOT automatically backfilled.').pack(anchor='w')
        refresh()
    def admin(self,p):
        super().admin(p)
        if self.user and self.user['role']=='admin':
            ttk.Separator(p).pack(fill='x',pady=16)
            ttk.Label(p,text='Database management',font=('Segoe UI',14,'bold')).pack(anchor='w',pady=6)
            ttk.Label(p,text='Archive the entire current database to a separate file and start with a fresh database.\\n'
                'The signed-in administrator login and business branding are retained; transactions, products, customers, and other employee accounts are reset.',
                wraplength=800).pack(anchor='w',pady=6)
            self.button(p,'Archive current database and create new',self.new_database)

    def new_database(self):
        """Archive live SQLite database then atomically switch to an empty database."""
        if not self.user or self.user['role']!='admin':
            raise PermissionError('Administrator access required.')
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        destination=filedialog.asksaveasfilename(
            title='Save current business database archive',
            defaultextension='.db',initialfile=f'TDZIGNS_business_archive_{stamp}.db',
            filetypes=[('SQLite database','*.db')])
        if not destination:return
        archive=Path(destination).resolve()
        if archive==DB.resolve() or archive in [Path(str(DB)+x).resolve() for x in ('-wal','-shm')]:
            raise ValueError('Choose a different location from the active database.')
        if archive.exists():
            raise ValueError('Archive filename already exists. Choose a new filename to avoid overwriting a backup.')
        if not messagebox.askyesno('Create fresh database',
                'This will archive all current business data to:\\n'+str(archive)+
                '\\n\\nThen start a NEW EMPTY database. Only your administrator login and company branding will be carried over. '
                'Other employee accounts must be created again.\\n\\nContinue?'):
            return
        # Generate a new database with the same installed schema, but no business rows.
        import uuid
        temporary=DATA/('new_business_'+uuid.uuid4().hex+'.db')
        created_archive=False
        try:
            fresh=sqlite3.connect(temporary)
            try:
                fresh.execute('PRAGMA foreign_keys=ON')
                # Create tables first, then indexes/triggers, including migration-created objects.
                objects=self.db.execute("""SELECT type,name,sql FROM sqlite_master
                    WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
                    ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END,name""").fetchall()
                for obj in objects:
                    fresh.execute(obj['sql'])
                # Retain only the current admin and business identity settings.
                fresh.execute('INSERT INTO users(id,username,password,role) VALUES(?,?,?,?)',
                    tuple(self.db.execute('SELECT id,username,password,role FROM users WHERE id=?',
                                          (self.user['id'],)).fetchone()))
                for row in self.db.execute("SELECT key,value FROM settings"):
                    fresh.execute('INSERT INTO settings(key,value) VALUES(?,?)',(row['key'],row['value']))
                config=self.db.execute('SELECT manifest_url,check_at_launch FROM update_settings WHERE id=1').fetchone()
                if config:
                    fresh.execute('INSERT INTO update_settings(id,manifest_url,check_at_launch) VALUES(1,?,?)',tuple(config))
                fresh.commit()
                result=fresh.execute('PRAGMA integrity_check').fetchone()[0]
                if result!='ok':raise RuntimeError('New database integrity check failed: '+result)
            finally:fresh.close()
            # SQLite's backup API produces a consistent snapshot, including uncheckpointed WAL data.
            with sqlite3.connect(str(archive)) as backup:self.db.backup(backup)
            created_archive=True
            with sqlite3.connect(str(archive)) as check:
                if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise RuntimeError('Archive verification failed.')
            # The archive exists and is verified before touching the live database.
            self.db.close()
            try:
                os.replace(temporary,DB)
                for suffix in ('-wal','-shm'):
                    Path(str(DB)+suffix).unlink(missing_ok=True)
            except Exception:
                self.db=sqlite3.connect(DB);self.db.row_factory=sqlite3.Row
                self.db.execute('PRAGMA foreign_keys=ON')
                raise
            self.db=sqlite3.connect(DB)
            self.db.row_factory=sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            schema(self.db)
            self.user=dict(self.db.execute('SELECT * FROM users WHERE id=?',(self.user['id'],)).fetchone())
            self._update_checked=True
            self.home()
            messagebox.showinfo('New database ready',
                'Your previous database was saved to:\\n'+str(archive)+
                '\\n\\nThe new database is active. Keep your archive in a safe location.')
        finally:
            temporary.unlink(missing_ok=True)

    def edit_document_templates(self):
        if not self.user or self.user['role']!='admin':
            raise PermissionError('Administrator access required to edit document templates.')
        open_visual_template_editor(self.root,self.db,DATA)

    def settings_tab(self,p):
        ttk.Label(p,text='TDZIGNS LLC | Branding and updates',font=('Segoe UI',17,'bold')).pack(anchor='w',pady=10)
        if self.user['role']!='admin':
            ttk.Label(p,text='Administrator access required.').pack(anchor='w');return
        def branding():
            fields=[('business_name','Business name'),('business_address','Address'),('business_phone','Phone'),('business_email','Email')]
            v=self.form('Business identity',fields,{k:self.setting(k) for k,_ in fields})
            if not v:return
            with self.db:
                for k,val in v.items():self.db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,val))
        def logo():
            path=filedialog.askopenfilename(filetypes=[('Images','*.png *.jpg *.jpeg')])
            if not path:return
            dest=DATA/('business_logo'+Path(path).suffix.lower());shutil.copy2(path,dest)
            with self.db:self.db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('logo_path',str(dest)))
        self.button(p,'Edit business details',branding);self.button(p,'Choose company logo',logo)
        ttk.Separator(p).pack(fill='x',pady=12)
        ttk.Label(p,text='Document templates',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=5)
        ttk.Label(p,text='Design custom estimate, invoice, and PO PDFs by dragging objects onto the page. Preview, save, or use classic settings.',wraplength=850).pack(anchor='w')
        self.button(p,'Open Visual Template Designer',self.edit_document_templates)
        def restore_classic():
            from visual_templates import reset as reset_visual
            if not messagebox.askyesno('Use classic PDF templates',
                'Switch estimate, invoice and PO exports back to classic templates? Saved visual designs will be removed.'):return
            for kind in ('Estimate','Invoice','PO'):reset_visual(self.db,kind)
            messagebox.showinfo('Classic templates active','Classic document template settings are active again.')
        self.button(p,'Edit classic template settings',lambda:open_template_editor(self.root,self.db,DATA))
        self.button(p,'Use classic PDF layouts',restore_classic)
        ttk.Separator(p).pack(fill='x',pady=16)
        ttk.Label(p,text=f'Installed version: {VERSION}').pack(anchor='w')
        row=self.db.execute('SELECT * FROM update_settings WHERE id=1').fetchone()
        url=tk.StringVar(value=row['manifest_url'] or RELEASE_MANIFEST_URL);auto=tk.BooleanVar(value=bool(row['check_at_launch']))
        ttk.Label(p,text='GitHub Releases update feed (configured automatically; advanced users may change it)').pack(anchor='w',pady=4)
        ttk.Entry(p,textvariable=url,width=90).pack(anchor='w',pady=4)
        ttk.Checkbutton(p,text='Check for updates at sign-in (requires internet)',variable=auto).pack(anchor='w',pady=6)
        def save():
            if url.get().strip() and not url.get().strip().lower().startswith('https://'):raise ValueError('Use an HTTPS manifest URL.')
            with self.db:self.db.execute('UPDATE update_settings SET manifest_url=?,check_at_launch=? WHERE id=1',(url.get().strip(),int(auto.get())))
            messagebox.showinfo('Saved','Update preferences saved.')
        self.button(p,'Save update settings',save)
        installed=Path(sys.executable).resolve() if getattr(sys,'frozen',False) else Path(__file__).resolve()
        ttk.Label(p,text='Application location: '+str(installed),wraplength=900).pack(anchor='w',pady=5)
        if getattr(sys,'frozen',False) and sys.platform=='win32':
            install_target,is_temporary=choose_install_target(installed,os.environ.get('LOCALAPPDATA',str(DATA.parent)),os.environ.get('TEMP',''))
            if is_temporary:
                ttk.Label(p,text='WARNING: Running from a temporary ZIP folder. The next update will install BusinessDesk permanently at:\n'+install_target,
                    foreground='#B45309',wraplength=900).pack(anchor='w',pady=7)

        last=read_status(DATA)
        if last:
            state=last.get('status','unknown')
            detail=last.get('message','')
            ttk.Label(p,text=f'Last update: {state} — {detail}',wraplength=900).pack(anchor='w',pady=4)
        self.button(p,'Open application folder',self.open_application_folder)
        self.button(p,'Open update log',self.open_update_log)
        self.button(p,'Check GitHub for updates',lambda:self.check_updates(url.get().strip() or RELEASE_MANIFEST_URL))
        self.button(p,'Install local Windows Setup or update ZIP',self.choose_local_update)
        self.button(p,'Select update folder',self.choose_update_folder)

        ttk.Label(p,text='Check GitHub for the latest release and install its verified Windows Setup package. Setup registers BusinessDesk in Windows Installed Apps and preserves your separate business database. Older releases can still use ZIP updates.',wraplength=850).pack(anchor='w',pady=12)
    def open_application_folder(self):
        path=Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
        if sys.platform=='win32':os.startfile(str(path))
        else:messagebox.showinfo('Application folder',str(path))

    def open_update_log(self):
        folder=DATA/'updates';folder.mkdir(parents=True,exist_ok=True)
        log=folder/'installation.log'
        if sys.platform=='win32':
            if log.is_file():os.startfile(str(log))
            else:os.startfile(str(folder))
        else:messagebox.showinfo('Update diagnostics',str(log))

    def choose_update_folder(self):
        folder=filedialog.askdirectory(title='Choose folder containing BusinessDesk Setup EXE or update ZIP')
        if not folder:return
        packages=sorted(list(Path(folder).glob('*.zip'))+list(Path(folder).glob('TDZIGNS_BusinessDesk_Setup_*.exe')))
        if not packages:
            raise ValueError('No BusinessDesk setup EXE or update ZIP found in the selected directory.')
        selected=filedialog.askopenfilename(title='Select update package',initialdir=folder,
            filetypes=[('BusinessDesk installation packages','*.exe *.zip')])
        if selected:self.load_local_update(Path(selected))

    def choose_local_update(self):
        selected=filedialog.askopenfilename(title='Select Windows update package',
            filetypes=[('BusinessDesk installation packages','*.exe *.zip')])
        if selected:self.load_local_update(Path(selected))

    def load_local_update(self,package):
        if self.user['role']!='admin':raise PermissionError('Administrator login required.')
        if not package.is_file():raise FileNotFoundError('Selected update file does not exist.')
        if package.stat().st_size>200*1024*1024:raise ValueError('Update exceeds 200 MB.')
        if package.suffix.lower()=='.exe':
            validate_setup_file(package)
        elif package.suffix.lower()=='.zip':
            with zipfile.ZipFile(package) as archive:
                names=[n for n in archive.namelist() if not n.endswith('/')]
                inspect_release(package)
                if not valid_release_names(names):
                    if any(n.endswith('.py') for n in names):
                        raise ValueError('This is a source-code ZIP, not an installable update. Build the Windows EXE first.')
                    raise ValueError('Update ZIP must contain the EXE and _internal Python runtime folder at its root.')
                if archive.getinfo('TDZIGNS_BusinessDesk.exe').file_size<100000:
                    raise ValueError('Windows executable is unexpectedly small.')
        else:raise ValueError('Choose a BusinessDesk Setup EXE or complete GitHub release ZIP.')
        match=re.search(r'(\d+\.\d+\.\d+)',package.stem)
        version=match.group(1) if match else 'unknown'
        if version!='unknown' and tuple(map(int,version.split('.')))<=tuple(map(int,VERSION.split('.'))):
            raise ValueError('Selected update version is not newer than the installed version.')
        with package.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
        checksum=package.with_suffix('.sha256')
        if checksum.exists():
            expected=checksum.read_text(encoding='utf-8').strip().split()[0].lower()
            if not re.fullmatch(r'[0-9a-f]{64}',expected) or expected!=digest:
                raise ValueError('Local SHA-256 checksum mismatch.')
        elif not messagebox.askyesno('Confirm trusted update',
              'No checksum file was found. Only install an EXE from your trusted release source. Continue?'):
            return
        self.offer_install(package,digest,version)

    def check_updates(self,url):
        url=url or RELEASE_MANIFEST_URL
        if not url.lower().startswith('https://'):raise ValueError('Only HTTPS update manifests are allowed.')
        def worker():
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'TDZIGNS-BusinessDesk-Updater/2.8'}),timeout=15) as resp:
                    if int(resp.headers.get('Content-Length') or '0')>65536:raise ValueError('Update manifest is too large.')
                    manifest=json.loads(resp.read(65537))
                    if not isinstance(manifest,dict):raise ValueError('Invalid manifest response.')
                version,download,digest,kind=select_update_asset(
                    manifest, trusted_prefix=TRUSTED_RELEASE_PREFIX if url==RELEASE_MANIFEST_URL else None)
                # The preferred asset is a standard Windows installer, which
                # handles files, shortcuts and Installed Apps registration.
                # Older GitHub releases remain ZIP compatible.
                def ask():
                    if tuple(map(int,version.split('.')))<=tuple(map(int,VERSION.split('.'))):
                        messagebox.showinfo('Updates','Already up to date; no newer release available.');return
                    if not messagebox.askyesno('Update available',f'Version {version} is available. Download the verified package?'):return
                    threading.Thread(target=lambda:self.download_update(download,digest,version),daemon=True).start()
                self.root.after(0,ask)
            except Exception as e:
                msg = ('No published GitHub Release update was found. Publish a version tag (for example v2.8.0) and allow the Windows release workflow to finish first.' if getattr(e,'code',None)==404 and url==RELEASE_MANIFEST_URL else str(e))
                self.root.after(0,lambda error=msg:messagebox.showerror('Update check failed',error))
        threading.Thread(target=worker,daemon=True).start()
    def download_update(self,url,digest,version):
        try:
            folder=DATA/'updates';folder.mkdir(exist_ok=True)
            safe=''.join(c for c in version if c.isalnum() or c in '.-_')[:45]
            target=folder/(f'TDZIGNS_BusinessDesk_Setup_{safe}.exe' if url.lower().split('?',1)[0].endswith('.exe') else f'BusinessDesk_{safe}.zip')
            temp=target.with_suffix('.download')
            sha=hashlib.sha256()
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'TDZIGNS-BusinessDesk-Updater/2.8'}),timeout=40) as resp,open(temp,'wb') as f:
                length=0
                while True:
                    chunk=resp.read(65536)
                    if not chunk:break
                    length+=len(chunk)
                    if length>200*1024*1024:raise ValueError('Update package exceeds 200 MB limit.')
                    sha.update(chunk);f.write(chunk)
            if sha.hexdigest()!=digest:
                temp.unlink(missing_ok=True);raise ValueError('SHA-256 checksum mismatch. Update discarded.')
            temp.replace(target)
            self.root.after(0,lambda:self.offer_install(target,digest,version))
        except Exception as e:self.root.after(0,lambda msg=str(e):messagebox.showerror('Update failed',msg))


    def offer_install(self,package,digest,version):
        if not (getattr(sys,'frozen',False) and sys.platform=='win32'):
            messagebox.showinfo('Verified update downloaded',
                'The update has been verified and saved to:\n'+str(package)+
                '\n\nAutomatic installation requires the packaged Windows EXE. Build and launch the EXE once using build_windows.bat.')
            return
        if self.user['role']!='admin':
            messagebox.showwarning('Administrator required','Sign in as an administrator to install updates.')
            return
        target,temporary=choose_install_target(Path(sys.executable).resolve(),os.environ.get('LOCALAPPDATA',str(DATA.parent)),os.environ.get('TEMP',''))
        explanation=('BusinessDesk is running from a temporary ZIP location. It will be installed permanently, and desktop/Start Menu shortcuts will be created.'
                     if temporary else 'The installed application folder will be updated and its previous version backed up.')
        installer_package=Path(package).suffix.lower()=='.exe'
        if messagebox.askyesno('Install update',
            f'Install TDZIGNS BusinessDesk {version} now?\n\nInstallation location:\n{target}\n\n{explanation}\n\n'+
            ('Windows Setup will register the app, create shortcuts, and preserve your separate business database.\n' if installer_package
             else 'The installed application folder will be replaced, keeping a backup.\n')+
            'BusinessDesk will close and restart after installation. Save your work first.'):
            self.install_update(package,digest,version)

    def install_update(self,package,digest,version=''):
        if not (getattr(sys,'frozen',False) and sys.platform=='win32'):
            raise ValueError('Automatic installation is only supported from the packaged Windows EXE.')
        if self.user['role']!='admin':raise PermissionError('Administrator login required.')
        if getattr(self,'_updating',False):raise RuntimeError('An update is already being prepared.')
        if Path(package).suffix.lower()=='.exe':
            self.install_setup_update(package,digest,version)
            return
        current_executable=Path(sys.executable).resolve()
        install_target,migrating=choose_install_target(current_executable,os.environ.get('LOCALAPPDATA',str(DATA.parent)),os.environ.get('TEMP',''))
        executable=Path(install_target)
        if migrating:
            # Always use per-user permanent installation folder, never temporary copies.
            executable.parent.mkdir(parents=True,exist_ok=True)
        if hashlib.sha256(Path(package).read_bytes()).hexdigest()!=digest:
            raise ValueError('Update checksum changed; installation cancelled.')
        if Path(package).suffix.lower()=='.zip':
            with zipfile.ZipFile(package) as z:
                names=[n for n in z.namelist() if not n.endswith('/')]
                inspect_release(package)
                if not valid_release_names(names) or z.getinfo('TDZIGNS_BusinessDesk.exe').file_size<100000:
                    raise ValueError('Update ZIP must contain the EXE and _internal Python runtime folder at its root.')
        elif Path(package).suffix.lower()=='.exe':
            raise ValueError('Select the GitHub release ZIP with the EXE and _internal runtime.')
        else:raise ValueError('Update must be the GitHub release .zip.')
        updates=DATA/'updates';updates.mkdir(parents=True,exist_ok=True)
        backup=updates/('pre_update_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
        with sqlite3.connect(str(backup)) as target:self.db.backup(target)
        helper_src=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'update_installer.ps1'
        if not helper_src.is_file():raise FileNotFoundError('Installer helper missing from build.')
        helper=updates/('update_installer_'+uuid.uuid4().hex+'.ps1')
        shutil.copy2(helper_src,helper)
        # Save the location even if the helper is unable to run.
        status={'status':'handoff','version':version,'target':str(executable),
                'message':'Closing the application; the installer will continue in a separate process.',
                'log':str(updates/'installation.log')}
        (updates/STATUS_NAME).write_text(json.dumps(status,indent=2),encoding='utf-8')
        args=['powershell.exe','-NoProfile','-NonInteractive','-STA','-ExecutionPolicy','Bypass',
              '-File',str(helper),'-Package',str(package),'-Target',str(executable),
              '-ProcessIdToWait',str(os.getpid()),'-DataDir',str(DATA),'-ExpectedSha256',digest,'-Version',str(version if re.fullmatch(r'\d+\.\d+\.\d+',str(version)) else '')]
        if migrating:
            args.append('-CreateShortcuts')
            if not executable.exists():args.append('-AllowFreshInstall')
        # Keep this GUI running until the installer has VALIDATED and unpacked
        # the update. Previously, merely starting PowerShell closed the app,
        # even when that installer failed before doing any useful work.
        attempt=uuid.uuid4().hex
        handoff=updates/('handoff_'+attempt+'.ready')
        args.extend(['-HandoffFile',str(handoff),'-AttemptId',attempt])
        status['attempt_id']=attempt
        (updates/STATUS_NAME).write_text(json.dumps(status,indent=2),encoding='utf-8')
        # Permanent manual escape hatch if restarting ever fails on this PC.
        # The EXE stays in its original path; the updater does not install elsewhere.
        manual=updates/'Reopen BusinessDesk.cmd'
        manual.write_text('@echo off\nstart "" "'+str(executable)+'"\n',encoding='utf-8')
        # A normal, visible console avoids silent DETACHED_PROCESS failures.
        # The updater and its error messages remain visible while it runs.
        flags=getattr(subprocess,'CREATE_NEW_CONSOLE',0)
        try:
            worker=subprocess.Popen(args,creationflags=flags,close_fds=True)
        except OSError as exc:
            (updates/STATUS_NAME).write_text(json.dumps({**status,'status':'failed','message':str(exc)},indent=2),encoding='utf-8')
            raise RuntimeError('Could not start PowerShell updater; BusinessDesk is still open: '+str(exc)) from exc
        self._updating=True
        self._update_worker=worker
        self._update_handoff=handoff
        self._update_attempt=attempt
        self._update_deadline=datetime.now().timestamp()+75
        self._poll_update_handoff()

    def install_setup_update(self,package,digest,version):
        """Launch a detached verified Windows Setup, without closing before handoff."""
        if not (getattr(sys,'frozen',False) and sys.platform=='win32'):
            raise RuntimeError('Windows Setup auto-installation requires the packaged Windows application.')
        if self.user['role']!='admin':raise PermissionError('Administrator login required.')
        validate_setup_file(package)
        with open(package,'rb') as f:
            actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=digest:raise ValueError('Windows Setup checksum mismatch; installation cancelled.')
        target,_=choose_install_target(Path(sys.executable).resolve(),
                                       os.environ.get('LOCALAPPDATA',str(DATA.parent)),
                                       os.environ.get('TEMP',''))
        updates=DATA/'updates';updates.mkdir(parents=True,exist_ok=True)
        backup=updates/('pre_setup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
        with sqlite3.connect(str(backup)) as destination:self.db.backup(destination)
        helper_src=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'installer_update.ps1'
        if not helper_src.is_file():
            raise FileNotFoundError('Windows Setup updater helper is missing from this build.')
        helper=updates/('installer_update_'+uuid.uuid4().hex+'.ps1')
        shutil.copy2(helper_src,helper)
        attempt=uuid.uuid4().hex
        handoff=updates/('handoff_'+attempt+'.ready')
        status={'status':'handoff','version':version,'attempt_id':attempt,'target':str(target),
                'message':'Verifying Windows Setup before closing the application.',
                'log':str(updates/'installation.log')}
        (updates/STATUS_NAME).write_text(json.dumps(status,indent=2),encoding='utf-8')
        args=['powershell.exe','-NoProfile','-NonInteractive','-STA','-ExecutionPolicy','Bypass',
              '-File',str(helper),'-Installer',str(package),'-Target',str(target),
              '-ProcessIdToWait',str(os.getpid()),'-DataDir',str(DATA),
              '-ExpectedSha256',digest,'-Version',str(version),
              '-HandoffFile',str(handoff),'-AttemptId',attempt]
        (updates/'Reopen BusinessDesk.cmd').write_text('@echo off\nstart "" "'+str(target)+'"\n',encoding='utf-8')
        try:
            worker=subprocess.Popen(args,creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0),close_fds=True)
        except OSError as exc:
            (updates/STATUS_NAME).write_text(json.dumps({**status,'status':'failed','message':str(exc)},indent=2),encoding='utf-8')
            raise RuntimeError('Unable to launch Windows Setup helper; the application remains open.') from exc
        self._updating=True
        self._update_worker=worker
        self._update_handoff=handoff
        self._update_attempt=attempt
        self._update_deadline=datetime.now().timestamp()+75
        self._poll_update_handoff()

    def _poll_update_handoff(self):
        # Tk's mainloop continues to run while the helper verifies the package.
        # This cannot deadlock with PowerShell's wait on the parent process.
        marker=self._update_handoff
        if marker.is_file():
            try:
                if marker.read_text(encoding='utf-8-sig').strip()!='PREPARED':
                    raise ValueError('Unexpected updater handoff confirmation')
                marker.unlink(missing_ok=True)
                self.db.commit()
                self.db.close()
                self.root.destroy()
            except Exception as exc:
                self._updating=False
                messagebox.showerror('Update handoff error',str(exc))
            return
        status=read_status(DATA) or {}
        if status.get('attempt_id')==self._update_attempt and status.get('status') in ('failed','rollback_failed'):
            reason=status.get('message','Update could not be prepared.')
            self._updating=False
            messagebox.showerror('Update failed — app remains open',reason+'\n\nSee: '+str(DATA/'updates'/'installation.log'))
            return
        code=self._update_worker.poll()
        if code is not None or datetime.now().timestamp()>=self._update_deadline:
            self._updating=False
            reason=('Installer exited with code '+str(code) if code is not None else
                    'Installer did not confirm that the package was ready within 75 seconds.')
            messagebox.showerror('Update could not start',reason+'\n\nBusinessDesk remains open. See: '+str(DATA/'updates'/'installation.log'))
            return
        self.root.after(250,self._poll_update_handoff)

if __name__=='__main__':BusinessDesk().run()
