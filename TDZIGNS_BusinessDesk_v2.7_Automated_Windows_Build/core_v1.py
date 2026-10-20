
"""BusinessDesk v1 — offline Windows business manager (Python standard library)."""
import csv, hashlib, hmac, os, secrets, shutil, sqlite3, sys, tkinter as tk
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from tkinter import ttk, messagebox, filedialog, simpledialog
from responsive_ui import ResponsiveToolbar

APP="BusinessDesk"
DATA=Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP
DATA.mkdir(parents=True, exist_ok=True)
DB=DATA/"business.db"

def cents(value):
    try:
        n=Decimal(str(value).replace("$","").replace(",",""))
        if not n.is_finite() or n < 0: raise ValueError()
        return int((n*100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation,ValueError):
        raise ValueError("Enter a nonnegative dollar amount.")
def money(n): return f"${n/100:,.2f}"
def hashed(password, salt=None):
    salt=salt or secrets.token_bytes(16)
    return salt.hex()+":"+hashlib.pbkdf2_hmac("sha256",password.encode(),salt,260000).hex()
def verify(password, encoded):
    try:
        s,d=encoded.split(":")
        return hmac.compare_digest(hashed(password,bytes.fromhex(s)),encoded)
    except Exception: return False

def connect():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff')));
    CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT,
      phone TEXT, address TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, description TEXT DEFAULT '', price INTEGER NOT NULL CHECK(price>=0),
      cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0), qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0));
    CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, kind TEXT NOT NULL
      CHECK(kind IN ('Estimate','Invoice')), customer_id INTEGER NOT NULL REFERENCES customers(id),
      created TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open',
      subtotal INTEGER NOT NULL, tax INTEGER NOT NULL, total INTEGER NOT NULL,
      notes TEXT DEFAULT '', created_by INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS document_items(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL
      REFERENCES documents(id), product_id INTEGER REFERENCES products(id),
      description TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0),
      unit_price INTEGER NOT NULL, line_total INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, spent_on TEXT NOT NULL,
      category TEXT NOT NULL, vendor TEXT, description TEXT, amount INTEGER NOT NULL CHECK(amount>=0));
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL
      REFERENCES documents(id), paid_on TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
      method TEXT DEFAULT '');
    """)
    db.commit()
    return db

class App:
    def __init__(self):
        self.db=connect()
        self.root=tk.Tk()
        self.root.title("BusinessDesk v1 | Offline Business Manager")
        self.root.geometry("1120x720")
        self.root.minsize(850,560)
        style=ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("Treeview",rowheight=26)
        style.configure("Heading",font=("Segoe UI",10,"bold"))
        self.user=None
        self.login()
    def clear(self):
        for w in self.root.winfo_children(): w.destroy()
    def form(self, title, fields, initial=None):
        win=tk.Toplevel(self.root);win.title(title);win.transient(self.root);win.grab_set()
        win.resizable(False,False)
        entries={}
        for i,(key,label) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,padx=12,pady=7,sticky="w")
            e=ttk.Entry(win,width=44)
            e.grid(row=i,column=1,padx=12,pady=7)
            if initial and key in initial and initial[key] is not None: e.insert(0,str(initial[key]))
            entries[key]=e
        out={}
        def save():
            out.update({k:v.get().strip() for k,v in entries.items()});win.destroy()
        ttk.Button(win,text="Save",command=save).grid(row=len(fields),column=1,pady=15,sticky="e",padx=12)
        win.bind("<Return>",lambda e:save())
        win.wait_window()
        return out or None
    def error(self,exc): messagebox.showerror("BusinessDesk",str(exc),parent=self.root)
    def login(self):
        self.clear()
        panel=ttk.Frame(self.root,padding=50);panel.pack(expand=True)
        ttk.Label(panel,text="BusinessDesk",font=("Segoe UI",26,"bold")).pack(pady=12)
        count=self.db.execute("SELECT count(*) FROM users").fetchone()[0]
        if not count:
            ttk.Label(panel,text="First launch: create the administrator account").pack(pady=10)
        name=tk.StringVar();pw=tk.StringVar()
        ttk.Label(panel,text="Username").pack(anchor="w")
        ttk.Entry(panel,textvariable=name,width=34).pack(pady=6)
        ttk.Label(panel,text="Password").pack(anchor="w")
        ttk.Entry(panel,textvariable=pw,show="*",width=34).pack(pady=6)
        def submit():
            try:
                if not name.get().strip() or len(pw.get())<10: raise ValueError("Enter a username and password (minimum 10 characters).")
                if not count:
                    confirm=simpledialog.askstring("Confirm password","Re-enter administrator password",show="*",parent=self.root)
                    if confirm!=pw.get(): raise ValueError("Passwords do not match.")
                    with self.db: self.db.execute("INSERT INTO users(username,password,role) VALUES(?,?,'admin')",(name.get().strip(),hashed(pw.get())))
                row=self.db.execute("SELECT * FROM users WHERE username=?",(name.get().strip(),)).fetchone()
                if not row or not verify(pw.get(),row["password"]): raise ValueError("Invalid username or password.")
                self.user=dict(row);self.home()
            except Exception as e: self.error(e)
        ttk.Button(panel,text="Create administrator" if not count else "Sign in",command=submit).pack(pady=20)
        self.root.bind("<Return>",lambda e:submit() if self.user is None else None)
    def home(self):
        self.clear()
        bar=ttk.Frame(self.root,padding=10);bar.pack(fill="x")
        ttk.Label(bar,text="BusinessDesk",font=("Segoe UI",19,"bold")).pack(side="left",padx=8)
        ttk.Label(bar,text=f"Signed in: {self.user['username']} ({self.user['role']})").pack(side="right",padx=8)
        tabs=ttk.Notebook(self.root);tabs.pack(fill="both",expand=True,padx=12,pady=10)
        self.tabs=tabs
        for label,fn in [("Dashboard",self.dashboard),("Customers",self.customers),("Products / Catalog",self.products),
                         ("Estimates & Invoices",self.documents),("Expenses",self.expenses),("Reports",self.reports),
                         ("Administration",self.admin)]:
            frame=ttk.Frame(tabs,padding=12);tabs.add(frame,text=label);fn(frame)
    def table(self,parent,columns):
        frame=ttk.Frame(parent);frame.pack(fill="both",expand=True,pady=8)
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=columns,show="headings",selectmode="browse")
        for c in columns:
            tree.heading(c,text=c)
            name=str(c).casefold()
            width=(65 if name=='id' else (195 if any(x in name for x in ('address','email','name','description'))
                    else (115 if name in ('city','state','zip','phone') else 130)))
            tree.column(c,width=width,anchor="w",stretch=False)
        vertical=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
        horizontal=ttk.Scrollbar(frame,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky="nsew")
        vertical.grid(row=0,column=1,sticky="ns")
        horizontal.grid(row=1,column=0,sticky="ew")
        return tree
    def selected(self,tree):
        item=tree.selection()
        if not item: raise ValueError("Select a row first.")
        return int(tree.item(item[0],"values")[0])
    def button(self,parent,label,callback):
        if isinstance(parent,ResponsiveToolbar):
            return parent.add_action(label,lambda:self.safe(callback))
        return ttk.Button(parent,text=label,command=lambda:self.safe(callback)).pack(side="left",padx=4,pady=5)
    def safe(self,callback):
        try: callback()
        except Exception as e: self.error(e)
    def dashboard(self,p):
        invoices=self.db.execute("SELECT count(*),coalesce(sum(total),0) FROM documents WHERE kind='Invoice'").fetchone()
        received=self.db.execute("SELECT coalesce(sum(amount),0) FROM payments").fetchone()[0]
        expenses=self.db.execute("SELECT coalesce(sum(amount),0) FROM expenses").fetchone()[0]
        products=self.db.execute("SELECT count(*) FROM products").fetchone()[0]
        for title,value in [("Invoice total",money(invoices[1])),("Payments received",money(received)),
                            ("Unpaid balance",money(invoices[1]-received)),("Recorded expenses",money(expenses)),
                            ("Products in catalog",str(products))]:
            f=ttk.Frame(p,padding=10);f.pack(fill="x")
            ttk.Label(f,text=title,font=("Segoe UI",12)).pack(side="left")
            ttk.Label(f,text=value,font=("Segoe UI",15,"bold")).pack(side="right")
        ttk.Label(p,text="Figures are operational summaries, not a complete accounting ledger or tax report.",
                  foreground="#666").pack(anchor="w",pady=20)
        self.button(p,"Refresh dashboard",self.home)
    def customers(self,p):
        bar=ResponsiveToolbar(p);bar.pack(fill="x")
        tree=self.table(p,("ID","Name","Email","Phone","Address","Notes"))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute("SELECT * FROM customers ORDER BY name"):
                tree.insert("", "end",values=tuple(r[k] or "" for k in ("id","name","email","phone","address","notes")))
        def edit(new=False):
            id=None if new else self.selected(tree)
            row={} if new else dict(self.db.execute("SELECT * FROM customers WHERE id=?",(id,)).fetchone())
            v=self.form("Customer",[(x,x.title()) for x in ("name","email","phone","address","notes")],row)
            if not v:return
            if not v["name"]:raise ValueError("Customer name required.")
            with self.db:
                if new:self.db.execute("INSERT INTO customers(name,email,phone,address,notes) VALUES(?,?,?,?,?)",tuple(v.values()))
                else:self.db.execute("UPDATE customers SET name=?,email=?,phone=?,address=?,notes=? WHERE id=?",(*v.values(),id))
            refresh()
        self.button(bar,"Add customer",lambda:edit(True));self.button(bar,"Edit selected",edit)
        refresh()
    def products(self,p):
        bar=ResponsiveToolbar(p);bar.pack(fill="x")
        tree=self.table(p,("ID","SKU","Name","Description","Price","Cost","Stock"))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute("SELECT * FROM products ORDER BY name"):
                tree.insert("","end",values=(r["id"],r["sku"],r["name"],r["description"],money(r["price"]),money(r["cost"]),r["qty"]))
        def edit(new=False):
            id=None if new else self.selected(tree)
            row={} if new else dict(self.db.execute("SELECT * FROM products WHERE id=?",(id,)).fetchone())
            if row:row.update(price=f'{row["price"]/100:.2f}',cost=f'{row["cost"]/100:.2f}')
            v=self.form("Product",[(x,x.title()) for x in ("sku","name","description","price","cost","qty")],row)
            if not v:return
            if not v["sku"] or not v["name"]:raise ValueError("SKU and name are required.")
            price=cents(v["price"]);cost=cents(v["cost"]);qty=int(v["qty"])
            if qty<0:raise ValueError("Stock cannot be negative.")
            with self.db:
                if new:self.db.execute("INSERT INTO products(sku,name,description,price,cost,qty) VALUES(?,?,?,?,?,?)",
                                        (v["sku"],v["name"],v["description"],price,cost,qty))
                else:self.db.execute("UPDATE products SET sku=?,name=?,description=?,price=?,cost=?,qty=? WHERE id=?",
                                     (v["sku"],v["name"],v["description"],price,cost,qty,id))
            refresh()
        self.button(bar,"Add product",lambda:edit(True));self.button(bar,"Edit product",edit)
        self.button(bar,"Export catalog CSV",lambda:self.export("SELECT sku,name,description,price/100.0 AS price,cost/100.0 AS cost,qty FROM products"))
        refresh()
    def documents(self,p):
        bar=ResponsiveToolbar(p);bar.pack(fill="x")
        tree=self.table(p,("ID","Type","Customer","Date","Status","Total","Paid","Balance"))
        def refresh():
            tree.delete(*tree.get_children())
            q="""SELECT d.*,c.name AS customer,(SELECT coalesce(sum(amount),0) FROM payments WHERE document_id=d.id) AS paid
            FROM documents d JOIN customers c ON c.id=d.customer_id ORDER BY d.id DESC"""
            for r in self.db.execute(q):
                tree.insert("","end",values=(r["id"],r["kind"],r["customer"],r["created"],r["status"],
                                               money(r["total"]),money(r["paid"]),money(r["total"]-r["paid"])))
        def create():
            customers=list(self.db.execute("SELECT id,name FROM customers ORDER BY name"))
            if not customers:raise ValueError("Add a customer first.")
            if hasattr(self,'document_header_dialog'):
                v=self.document_header_dialog(customers)
            else:
                v=self.form("New document",[("kind","Type: Estimate or Invoice"),("customer","Customer ID: "+", ".join(f'{x["id"]}={x["name"]}' for x in customers[:12])),
                        ("tax","Tax rate (%), e.g. 5.5"),("notes","Notes")],{"kind":"Estimate","tax":"0"})
            if not v:return
            kind=v["kind"].title()
            if kind not in ("Estimate","Invoice"):raise ValueError("Type must be Estimate or Invoice.")
            cid=int(v["customer"])
            if cid not in [r["id"] for r in customers]:raise ValueError("Invalid customer ID.")
            rate=Decimal(v["tax"] or "0")
            if not rate.is_finite() or not 0<=rate<=100:raise ValueError("Tax must be between 0 and 100%.")
            if hasattr(self,'select_document_products'):
                items=self.select_document_products(kind,cid)
            else:
                items=[]
                while True:
                    product_id=simpledialog.askinteger("Add line item","Product ID (Cancel when finished).",
                                                         parent=self.root,minvalue=1)
                    if product_id is None:break
                    product=self.db.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
                    if not product:messagebox.showerror("Product","Invalid product ID");continue
                    qty=simpledialog.askinteger("Quantity",f'{product["name"]}: quantity',parent=self.root,minvalue=1)
                    if qty is None:continue
                    if kind=="Invoice" and qty>product["qty"]:
                        messagebox.showerror("Stock",f'Only {product["qty"]} units in stock.');continue
                    items.append((product_id,product["name"],qty,product["price"],qty*product["price"]))
            if not items:return
            subtotal=sum(i[4] for i in items)
            tax=int((Decimal(subtotal)*rate/100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
            if 'tax_exempt' in {r[1] for r in self.db.execute('PRAGMA table_info(customers)')}:
                if self.db.execute('SELECT tax_exempt FROM customers WHERE id=?',(cid,)).fetchone()[0]:
                    tax=0
            total=subtotal+tax
            if not messagebox.askyesno("Confirm",f"Create {kind} for {money(total)} with {len(items)} line item(s)?"):return
            with self.db:
                if kind=="Invoice":
                    required={}
                    for pid,_,qty,_,_ in items:required[pid]=required.get(pid,0)+qty
                    for pid,qty in required.items():
                        available=self.db.execute("SELECT qty FROM products WHERE id=?",(pid,)).fetchone()[0]
                        if qty>available:raise ValueError(f"Insufficient stock for product {pid}.")
                cur=self.db.execute("""INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by)
                       VALUES(?,?,?,'Open',?,?,?,?,?)""",(kind,cid,datetime.now().strftime("%Y-%m-%d"),subtotal,tax,total,v["notes"],self.user["id"]))
                docid=cur.lastrowid
                for pid,desc,qty,unit,line in items:
                    self.db.execute("INSERT INTO document_items(document_id,product_id,description,qty,unit_price,line_total) VALUES(?,?,?,?,?,?)",
                                    (docid,pid,desc,qty,unit,line))
                    if kind=="Invoice":
                        self.db.execute("UPDATE products SET qty=qty-? WHERE id=?",(qty,pid))
            refresh()
        def payment():
            id=self.selected(tree)
            doc=self.db.execute("SELECT * FROM documents WHERE id=?",(id,)).fetchone()
            if doc["kind"]!="Invoice":raise ValueError("Payments can only be recorded against invoices.")
            paid=self.db.execute("SELECT coalesce(sum(amount),0) FROM payments WHERE document_id=?",(id,)).fetchone()[0]
            remaining=doc["total"]-paid
            if remaining<=0:raise ValueError("Invoice already paid.")
            v=self.form("Record payment",[("amount",f"Amount (remaining {money(remaining)})"),("method","Method")])
            if not v:return
            amount=cents(v["amount"])
            if amount<=0 or amount>remaining:raise ValueError("Payment must be greater than zero and no more than the balance.")
            with self.db:
                self.db.execute("INSERT INTO payments(document_id,paid_on,amount,method) VALUES(?,?,?,?)",
                                (id,datetime.now().strftime("%Y-%m-%d"),amount,v["method"]))
                if amount==remaining:self.db.execute("UPDATE documents SET status='Paid' WHERE id=?",(id,))
            refresh()
        def print_doc():
            id=self.selected(tree)
            d=self.db.execute("""SELECT d.*,c.name,c.email,c.address FROM documents d
                JOIN customers c ON c.id=d.customer_id WHERE d.id=?""",(id,)).fetchone()
            lines=[f'{d["kind"].upper()} #{id}',f'Date: {d["created"]}',f'Customer: {d["name"]}',
                   f'Email: {d["email"] or ""}',f'Address: {d["address"] or ""}',"","ITEMS"]
            for item in self.db.execute("SELECT * FROM document_items WHERE document_id=?",(id,)):
                lines.append(f'{item["description"]}  |  {item["qty"]} x {money(item["unit_price"])} = {money(item["line_total"])}')
            lines += ["",f'Subtotal: {money(d["subtotal"])}',f'Tax: {money(d["tax"])}',
                      f'Total: {money(d["total"])}',f'Notes: {d["notes"]}']
            filename=filedialog.asksaveasfilename(defaultextension=".txt",initialfile=f'{d["kind"]}_{id}.txt',
                                                   filetypes=[("Text document","*.txt")])
            if filename:
                Path(filename).write_text("\n".join(lines),encoding="utf-8")
                messagebox.showinfo("Saved","Document exported as printable text.")
        if hasattr(self,'register_home_action'):
            self.register_home_action('estimate.new',create)
        self.button(bar,"New estimate / invoice",create);self.button(bar,"Record payment",payment)
        self.button(bar,"Export selected document",print_doc)
        refresh()
    def expenses(self,p):
        bar=ResponsiveToolbar(p);bar.pack(fill="x")
        tree=self.table(p,("ID","Date","Category","Vendor","Description","Amount"))
        def refresh():
            tree.delete(*tree.get_children())
            for r in self.db.execute("SELECT * FROM expenses ORDER BY spent_on DESC,id DESC"):
                tree.insert("","end",values=(r["id"],r["spent_on"],r["category"],r["vendor"],r["description"],money(r["amount"])))
        def add():
            v=self.form("Record expense",[(x,x.title()) for x in ("spent_on","category","vendor","description","amount")],
                        {"spent_on":datetime.now().strftime("%Y-%m-%d")})
            if not v:return
            datetime.strptime(v["spent_on"],"%Y-%m-%d")
            if not v["category"]:raise ValueError("Category is required.")
            with self.db:self.db.execute("INSERT INTO expenses(spent_on,category,vendor,description,amount) VALUES(?,?,?,?,?)",
                                        (v["spent_on"],v["category"],v["vendor"],v["description"],cents(v["amount"])))
            refresh()
        if hasattr(self,'register_home_action'):
            self.register_home_action('expense.add',add)
        self.button(bar,"Add expense",add)
        self.button(bar,"Export expenses CSV",lambda:self.export("SELECT spent_on,category,vendor,description,amount/100.0 AS amount FROM expenses"))
        refresh()
    def export(self,sql):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV files","*.csv")])
        if not path:return
        cur=self.db.execute(sql)
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            writer=csv.writer(f);writer.writerow([x[0] for x in cur.description]);writer.writerows(cur)
        messagebox.showinfo("Export","CSV exported.")
    def reports(self,p):
        ttk.Label(p,text="Business reports",font=("Segoe UI",17,"bold")).pack(anchor="w",pady=12)
        queries=[
            ("Sales by month","SELECT substr(created,1,7) AS month,count(*) AS invoices,sum(total)/100.0 AS billed FROM documents WHERE kind='Invoice' GROUP BY substr(created,1,7) ORDER BY month"),
            ("Payments by month","SELECT substr(paid_on,1,7) AS month,sum(amount)/100.0 AS received FROM payments GROUP BY substr(paid_on,1,7) ORDER BY month"),
            ("Expenses by category","SELECT category,sum(amount)/100.0 AS spent FROM expenses GROUP BY category ORDER BY spent DESC"),
            ("Low stock (5 or fewer)","SELECT sku,name,qty FROM products WHERE qty<=5 ORDER BY qty,name"),
            ("Invoice balances","SELECT d.id,c.name,d.created,d.total/100.0 AS total,coalesce(sum(p.amount),0)/100.0 AS paid,(d.total-coalesce(sum(p.amount),0))/100.0 AS balance FROM documents d JOIN customers c ON c.id=d.customer_id LEFT JOIN payments p ON p.document_id=d.id WHERE d.kind='Invoice' GROUP BY d.id ORDER BY d.id DESC")
        ]
        for name,sql in queries:
            f=ttk.Frame(p);f.pack(fill="x",pady=7)
            ttk.Label(f,text=name,width=32).pack(side="left")
            self.button(f,"Export CSV",lambda q=sql:self.export(q))
        ttk.Label(p,text="Exports can be opened in Excel. Reports use recorded entries only.").pack(anchor="w",pady=12)
    def admin(self,p):
        ttk.Label(p,text="Administration",font=("Segoe UI",17,"bold")).pack(anchor="w",pady=10)
        actions=ResponsiveToolbar(p)
        actions.pack(fill="x",pady=(0,10))
        if self.user["role"]=="admin":
            def add_user():
                v=self.form("Add employee",[("username","Username"),("password","Temporary password (10+ characters)"),("role","Role: admin or staff")],
                            {"role":"staff"})
                if not v:return
                if len(v["password"])<10 or v["role"] not in ("admin","staff"):raise ValueError("Password 10+ characters; role admin or staff.")
                with self.db:self.db.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                                             (v["username"],hashed(v["password"]),v["role"]))
                messagebox.showinfo("Created","Employee account created.")
            self.button(actions,"Add employee login",add_user)
        def change_password():
            old=simpledialog.askstring("Password","Current password",show="*",parent=self.root)
            if old is None:return
            row=self.db.execute("SELECT password FROM users WHERE id=?",(self.user["id"],)).fetchone()
            if not verify(old,row["password"]):raise ValueError("Current password incorrect.")
            new=simpledialog.askstring("Password","New password (10+ characters)",show="*",parent=self.root)
            if new is None:return
            if len(new)<10:raise ValueError("Password must be at least 10 characters.")
            with self.db:self.db.execute("UPDATE users SET password=? WHERE id=?",(hashed(new),self.user["id"]))
            messagebox.showinfo("Updated","Password changed.")
        self.button(actions,"Change my password",change_password)
        if self.user["role"]=="admin":
            def backup():
                path=filedialog.asksaveasfilename(defaultextension=".db",initialfile=f'business_backup_{datetime.now():%Y%m%d}.db',
                                                  filetypes=[("SQLite backup","*.db")])
                if not path:return
                if Path(path).resolve()==DB.resolve():raise ValueError("Choose a different backup destination.")
                with sqlite3.connect(path) as target:self.db.backup(target)
                messagebox.showinfo("Backup","Database backup created. Store a copy somewhere safe.")
            self.button(actions,"Backup database",backup)
        self.button(actions,"Sign out",lambda:(setattr(self,"user",None),self.login()))
        ttk.Label(p,text=f"Local database: {DB}",wraplength=850).pack(anchor="w",pady=25)
    def run(self):self.root.mainloop()

if __name__=="__main__":App().run()
