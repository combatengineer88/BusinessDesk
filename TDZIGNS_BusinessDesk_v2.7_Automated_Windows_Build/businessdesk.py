"""TDZIGNS LLC BusinessDesk 2.0 — Windows/offline desktop business manager.
The local application uses the v1 core and extends it with v2 business workflows.
"""
import csv, hashlib, json, os, shutil, sqlite3, sys, tempfile, threading, urllib.request, webbrowser, subprocess, zipfile, re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from core_v1 import App as BaseApp, DB, DATA, cents, money
from sales_workflow import convert_estimate, record_invoice_payment

VERSION = '2.9.0'
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
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.utils import ImageReader
    from xml.sax.saxutils import escape
    settings={r['key']:r['value'] for r in db.execute('SELECT * FROM settings')}
    sty=getSampleStyleSheet(); sty.add(ParagraphStyle(name='RightTD',parent=sty['Normal'],alignment=TA_RIGHT))
    def para(t):return Paragraph(escape(str(t or '')).replace('\n','<br/>'),sty['Normal'])
    story=[]
    logo=settings.get('logo_path','')
    if logo and Path(logo).is_file():
        try:
            im=ImageReader(logo); w,h=im.getSize(); scale=min(1,170/w,75/h)
            story.append(Image(logo,width=w*scale,height=h*scale));story.append(Spacer(1,8))
        except Exception: pass
    story.append(Paragraph(escape(settings.get('business_name') or BUSINESS),sty['Title']))
    for key in ('business_address','business_phone','business_email'):
        if settings.get(key): story.append(para(settings[key]))
    story.append(Spacer(1,22))
    if kind=='PO':
        d=db.execute('SELECT p.*,s.name,s.address FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?',(record_id,)).fetchone()
        if not d: raise ValueError('Purchase order not found')
        heading=f'PURCHASE ORDER #{record_id}'
        recipient=f'Supplier: {d["name"]}'
        date=d['ordered_on']
        rows=[['Product','Quantity','Unit cost','Line total']]
        for x in db.execute('SELECT i.*,p.name FROM po_items i JOIN products p ON p.id=i.product_id WHERE i.po_id=?',(record_id,)):
            rows.append([para(x['name']),str(x['qty']),money(x['unit_cost']),money(x['qty']*x['unit_cost'])])
        subtotal=d['total'];tax=0;total=d['total']
    else:
        d=db.execute('SELECT d.*,c.name,c.address,c.email FROM documents d JOIN customers c ON c.id=d.customer_id WHERE d.id=?',(record_id,)).fetchone()
        if not d: raise ValueError('Document not found')
        heading=f'{d["kind"].upper()} #{record_id}'
        recipient=f'Customer: {d["name"]}'
        date=d['created']
        rows=[['Item','Quantity','Unit price','Line total']]
        for x in db.execute('SELECT * FROM document_items WHERE document_id=?',(record_id,)):
            rows.append([para(x['description']),str(x['qty']),money(x['unit_price']),money(x['line_total'])])
        subtotal=d['subtotal'];tax=d['tax'];total=d['total']
    story.extend([Paragraph(escape(heading),sty['Heading1']),para(recipient),para(f'Date: {date}'),Spacer(1,16)])
    t=Table(rows,colWidths=[250,65,90,90],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#183653')),
                           ('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f4f8')]),
                           ('BOTTOMPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9),
                           ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,-1),(-1,-1),0.5,colors.grey)]))
    story.extend([t,Spacer(1,16)])
    for name,value in [('Subtotal',subtotal),('Tax',tax),('TOTAL',total)]:
        if kind=='PO' and name=='Tax':continue
        story.append(Paragraph(f'<b>{name}: {escape(money(value))}</b>',sty['RightTD']))
        story.append(Spacer(1,5))
    if d['notes']:story.extend([Spacer(1,18),para('Notes: '+d['notes'])])
    SimpleDocTemplate(str(output),pagesize=letter,rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=35).build(story)


class BusinessDesk(BaseApp):
    def __init__(self):
        super().__init__()
        self.root.title(f'{BUSINESS} | BusinessDesk {VERSION}')
    def login(self):
        schema(self.db)
        self._update_checked=False
        super().login()
    def setting(self,key):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else ''
    def home(self):
        super().home()
        self.tabs.bind('<<NotebookTabChanged>>',self._on_tab_changed)
        self.root.title(f'{BUSINESS} | BusinessDesk {VERSION}')
        for label,fn in [('Suppliers / Purchase Orders',self.purchase_orders),('Accounting Ledger',self.accounting),('Updates / Branding',self.settings_tab)]:
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
        super().dashboard(p)
        estimates=self.db.execute("SELECT count(*),coalesce(sum(total),0) FROM documents WHERE kind='Estimate'").fetchone()
        ttk.Label(p,text=f'Open/created estimates: {estimates[0]}  |  Estimate value: {money(estimates[1])} (not invoiced revenue)',
                  font=('Segoe UI',11)).pack(anchor='w',pady=10)
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
        choice=messagebox.askyesnocancel('Import '+kind,
            f'Worksheet: {sheet}\nValid records: {len(rows)}\n\n{preview}\n\n'
            'Duplicate handling:\nYES = update matching records\n'
            'NO = skip matching records\nCANCEL = do not import.\n\n'
            'Products match by SKU; customers and suppliers match by name. '
            'Updating product quantities REPLACES current stock counts.')
        if choice is None:return
        mode='update' if choice else 'skip'
        created,updated,skipped=import_rows(self.db,kind,rows,mode)
        messagebox.showinfo('Import complete',
            f'Added: {created}\nUpdated: {updated}\nSkipped: {skipped}')
        self.home()

    def products(self,p):
        bar=ttk.Frame(p);bar.pack(fill='x')
        search=tk.StringVar()
        ttk.Label(bar,text='Search SKU / barcode:').pack(side='left',padx=3)
        entry=ttk.Entry(bar,textvariable=search,width=28);entry.pack(side='left',padx=4)
        tree=self.table(p,('ID','SKU','Barcode','Name','Description','Price','Cost','Stock','Image'))
        def refresh(*args):
            tree.delete(*tree.get_children())
            term='%'+search.get().strip()+'%'
            for r in self.db.execute('SELECT * FROM products WHERE sku LIKE ? OR barcode LIKE ? OR name LIKE ? ORDER BY name',(term,term,term)):
                tree.insert('','end',values=(r['id'],r['sku'],r['barcode'],r['name'],r['description'],money(r['price']),money(r['cost']),r['qty'],
                                                    'Yes' if r['image_path'] else ''))
        search.trace_add('write',refresh)
        def edit(new=False):
            id=None if new else self.selected(tree)
            row={} if new else dict(self.db.execute('SELECT * FROM products WHERE id=?',(id,)).fetchone())
            if row:row.update(price=f'{row["price"]/100:.2f}',cost=f'{row["cost"]/100:.2f}')
            v=self.form('Product',[(x,x.replace('_',' ').title()) for x in ('sku','barcode','name','description','price','cost','qty')],row)
            if not v:return
            if not v['sku'] or not v['name']:raise ValueError('SKU and name are required.')
            qty=int(v['qty'])
            if qty<0:raise ValueError('Stock cannot be negative.')
            values=(v['sku'],v['barcode'],v['name'],v['description'],cents(v['price']),cents(v['cost']),qty)
            with self.db:
                if new:self.db.execute('INSERT INTO products(sku,barcode,name,description,price,cost,qty) VALUES(?,?,?,?,?,?,?)',values)
                else:self.db.execute('UPDATE products SET sku=?,barcode=?,name=?,description=?,price=?,cost=?,qty=? WHERE id=?',(*values,id))
            refresh()
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
            except ImportError:
                photo=tk.PhotoImage(file=r['image_path'])
            label=tk.Label(win,image=photo);label.image=photo;label.pack(padx=10,pady=10)
        self.button(bar,'Add product',lambda:edit(True));self.button(bar,'Edit',edit)
        self.button(bar,'Import products from Excel',lambda:self.import_excel_dialog('products'))
        self.button(bar,'Attach image',attach_image);self.button(bar,'View image',view_image)
        self.button(bar,'Export catalog CSV',lambda:self.export('SELECT sku,barcode,name,description,price/100.0 AS price,cost/100.0 AS cost,qty,image_path FROM products'))
        ttk.Label(p,text='USB barcode scanners that type a barcode and Enter work in the search box.').pack(anchor='w')
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
            suppliers=list(self.db.execute('SELECT id,name FROM suppliers ORDER BY name'))
            if not suppliers:raise ValueError('Add a supplier first.')
            v=self.form('New purchase order',[('supplier','Supplier ID: '+', '.join(f'{x["id"]}={x["name"]}' for x in suppliers[:12])),('notes','Notes')])
            if not v:return
            sid=int(v['supplier'])
            if sid not in [x['id'] for x in suppliers]:raise ValueError('Unknown supplier ID.')
            items=[]
            while True:
                pid=simpledialog.askinteger('PO line','Product ID (Cancel to finish)',parent=self.root,minvalue=1)
                if pid is None:break
                product=self.db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                if not product:messagebox.showerror('Product','Unknown product');continue
                qty=simpledialog.askinteger('PO quantity',f'{product["name"]}: quantity',parent=self.root,minvalue=1)
                if qty is None:continue
                price=simpledialog.askstring('Unit cost',f'{product["name"]}: cost in dollars',initialvalue=f'{product["cost"]/100:.2f}',parent=self.root)
                if price is None:continue
                items.append((pid,qty,cents(price)))
            if not items:return
            total=sum(q*c for _,q,c in items)
            with self.db:
                cur=self.db.execute('INSERT INTO purchase_orders(supplier_id,ordered_on,notes,total) VALUES(?,?,?,?)',
                                    (sid,datetime.now().strftime('%Y-%m-%d'),v['notes'],total))
                self.db.executemany('INSERT INTO po_items(po_id,product_id,qty,unit_cost) VALUES(?,?,?,?)',[(cur.lastrowid,*i) for i in items])
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
        self.button(p,'Edit business details',branding);self.button(p,'Choose invoice logo',logo)
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
        self.button(p,'Check GitHub for updates',lambda:self.check_updates(url.get().strip() or RELEASE_MANIFEST_URL))
        self.button(p,'Install local ZIP or EXE',self.choose_local_update)
        self.button(p,'Select update folder',self.choose_update_folder)

        ttk.Label(p,text='Click Check GitHub for updates to download and install the newest published release. An administrator must approve installation. The repository must publish a tagged GitHub Release with a compiled update ZIP and manifest. Local ZIP/EXE installation remains available.',wraplength=850).pack(anchor='w',pady=12)
    def choose_update_folder(self):
        folder=filedialog.askdirectory(title='Choose folder containing a Windows update ZIP or EXE')
        if not folder:return
        packages=sorted(list(Path(folder).glob('*.zip'))+list(Path(folder).glob('*.exe')))
        if not packages:
            raise ValueError('No ZIP or EXE files were found in the selected directory.')
        selected=filedialog.askopenfilename(title='Select update package',initialdir=folder,
            filetypes=[('Windows updates','*.zip *.exe')])
        if selected:self.load_local_update(Path(selected))

    def choose_local_update(self):
        selected=filedialog.askopenfilename(title='Select Windows update package',
            filetypes=[('Windows updates','*.zip *.exe')])
        if selected:self.load_local_update(Path(selected))

    def load_local_update(self,package):
        if self.user['role']!='admin':raise PermissionError('Administrator login required.')
        if not package.is_file():raise FileNotFoundError('Selected update file does not exist.')
        if package.stat().st_size>200*1024*1024:raise ValueError('Update exceeds 200 MB.')
        if package.suffix.lower()=='.exe':
            with package.open('rb') as handle:
                if handle.read(2)!=b'MZ':raise ValueError('Selected file is not a Windows executable.')
            if package.stat().st_size<100000:raise ValueError('Selected executable is unexpectedly small.')
        elif package.suffix.lower()=='.zip':
            with zipfile.ZipFile(package) as archive:
                names=[n for n in archive.namelist() if not n.endswith('/')]
                if names!=['TDZIGNS_BusinessDesk.exe']:
                    if any(n.endswith('.py') for n in names):
                        raise ValueError('This is a source-code ZIP, not an installable update. Build the Windows EXE first.')
                    raise ValueError('Update ZIP must contain TDZIGNS_BusinessDesk.exe at its root.')
                if archive.getinfo(names[0]).file_size<100000:
                    raise ValueError('Windows executable is unexpectedly small.')
        else:raise ValueError('Choose a compiled Windows .exe or installable .zip file.')
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
                version=str(manifest['version']);download=str(manifest['url']);digest=str(manifest['sha256']).lower()
                if not re.fullmatch(r'\d+\.\d+\.\d+',version) or not download.startswith('https://') or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                    raise ValueError('Invalid update manifest.')
                if url==RELEASE_MANIFEST_URL and not download.startswith(TRUSTED_RELEASE_PREFIX):
                    raise ValueError('GitHub release manifest points outside the trusted repository.')
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
            target=folder/f'BusinessDesk_{safe}.zip'
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
        if messagebox.askyesno('Install update',
            f'Install TDZIGNS BusinessDesk {version} now?\n\nThe app will back up its database, close, replace the EXE, and restart.\nSave any other work first.'):
            self.install_update(package,digest)

    def install_update(self,package,digest):
        if not (getattr(sys,'frozen',False) and sys.platform=='win32'):
            raise ValueError('Automatic installation is only supported from the packaged Windows EXE.')
        if self.user['role']!='admin':raise PermissionError('Administrator login required.')
        executable=Path(sys.executable).resolve()
        if executable.name.lower()!='tdzigns_businessdesk.exe':
            raise ValueError('Unexpected executable name; cannot safely replace it.')
        if hashlib.sha256(Path(package).read_bytes()).hexdigest()!=digest:
            raise ValueError('Update checksum changed; installation cancelled.')
        if Path(package).suffix.lower()=='.zip':
            with zipfile.ZipFile(package) as z:
                names=[n for n in z.namelist() if not n.endswith('/')]
                if names!=['TDZIGNS_BusinessDesk.exe'] or z.getinfo(names[0]).file_size<100000:
                    raise ValueError('Update ZIP must contain TDZIGNS_BusinessDesk.exe at its root.')
        elif Path(package).suffix.lower()=='.exe':
            with open(package,'rb') as handle:
                if handle.read(2)!=b'MZ':raise ValueError('Not a valid Windows EXE.')
        else:raise ValueError('Update must be .exe or .zip.')
        updates=DATA/'updates';updates.mkdir(parents=True,exist_ok=True)
        backup=updates/('pre_update_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
        with sqlite3.connect(str(backup)) as target:self.db.backup(target)
        helper_src=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'update_installer.ps1'
        if not helper_src.is_file():raise FileNotFoundError('Installer helper missing from build.')
        helper=updates/'update_installer.ps1'
        shutil.copy2(helper_src,helper)
        args=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
              '-File',str(helper),'-Package',str(package),'-Target',str(executable),
              '-ProcessIdToWait',str(os.getpid()),'-DataDir',str(DATA),'-ExpectedSha256',digest]
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'DETACHED_PROCESS',0)
        subprocess.Popen(args,creationflags=flags,close_fds=True)
        self.root.destroy()

if __name__=='__main__':BusinessDesk().run()
