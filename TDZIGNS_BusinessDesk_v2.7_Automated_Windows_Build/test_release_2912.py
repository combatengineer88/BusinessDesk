"""v2.9.12 regression checks: discrete customer addresses, PDF reports, resized UI."""
import os
import tempfile
import sqlite3
import tkinter as tk
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
from tkinter import ttk
from report_export import export_report_pdf,format_report_cell
from address_utils import customer_address
from core_v1 import connect
from businessdesk import BusinessDesk,schema
from excel_import import parse as parse_excel, import_rows


class DataTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        import core_v1
        with patch.object(core_v1,'DB',Path(self.temp.name)/'test.db'):
            self.db=connect()
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO users(username,password,role) VALUES('admin','notused','admin')")
    def tearDown(self):self.db.close();self.temp.cleanup()

    def test_schema_is_upgrade_safe(self):
        schema(self.db)
        fields={r[1] for r in self.db.execute('PRAGMA table_info(customers)')}
        self.assertTrue({'city','state','zip_code','tax_exempt'}<=fields)
        self.assertEqual(customer_address('123 Main','Watertown','WI','53094'), '123 Main\nWatertown, WI 53094')

    def test_excel_customer_zip_preserves_leading_zero(self):
        values=parse_excel('customers',{'name':'Test Buyer','address':'22 Oak','city':'Boston','state':'MA','zip_code':'02110'})
        self.assertEqual(values['zip_code'],'02110')
        self.assertEqual(import_rows(self.db,'customers',[(2,values)],mode='skip'),(1,0,0))
        row=self.db.execute('SELECT address,city,state,zip_code FROM customers').fetchone()
        self.assertEqual(tuple(row),('22 Oak','Boston','MA','02110'))

    def test_customer_postal_details_in_visual_and_classic_pdf(self):
        from document_templates import render_document
        from visual_templates import render as render_visual_document
        with self.db:
            self.db.execute("INSERT INTO customers(name,address,city,state,zip_code) VALUES('Example','55 Lake St','Milwaukee','WI','53202')")
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty) VALUES('P1','Test Product',800,400,12)")
            self.db.execute("INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by) VALUES('Estimate',1,'2026-10-20','Open',1600,0,1600,'',1)")
            self.db.execute('INSERT INTO document_items(document_id,product_id,description,qty,unit_price,line_total) VALUES(1,1,\'Test Product\',2,800,1600)')
        for i,renderer in enumerate((render_document,render_visual_document)):
            path=Path(self.temp.name)/f'estimate_{i}.pdf'
            renderer(self.db,'Estimate',1,path)
            self.assertGreater(path.stat().st_size,1000)
            try:
                import fitz
                text=' '.join(page.get_text() for page in fitz.open(path))
                self.assertIn('Milwaukee',text)
                self.assertIn('53202',text)
            except ImportError:pass

    def test_branded_report_pdf(self):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('business_name','TEST BRAND LLC')")
            self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('business_email','sales@test.example')")
            self.db.execute("INSERT INTO customers(name) VALUES('Customer X')")
            self.db.execute("INSERT INTO documents(kind,customer_id,created,status,subtotal,tax,total,notes,created_by) VALUES('Invoice',1,'2026-10-19','Open',2200,0,2200,'',1)")
        path=Path(self.temp.name)/'sales.pdf'
        export_report_pdf(self.db,'Sales by month',"SELECT substr(created,1,7) AS month,count(*) AS invoices,sum(total)/100.0 AS billed FROM documents GROUP BY substr(created,1,7)",path)
        self.assertGreater(path.stat().st_size,1500)
        try:import fitz
        except ImportError:return
        with fitz.open(path) as pdf:
            text=pdf[0].get_text()
            for term in ['TEST BRAND LLC','Sales by month','2026-10','22.00','sales@test.example']:
                self.assertIn(term,text)
        self.assertEqual(format_report_cell('billed',22),'$22.00')

    def test_empty_and_multipage_reports(self):
        with self.db:
            for i in range(120):self.db.execute('INSERT INTO expenses(spent_on,category,vendor,description,amount) VALUES(?,?,?,?,?)',('2026-10-20',f'Category{i}',None,None,500))
        path=Path(self.temp.name)/'large.pdf'
        export_report_pdf(self.db,'Expense Categories','SELECT category,sum(amount)/100.0 AS spent FROM expenses GROUP BY category ORDER BY category',path)
        try:import fitz
        except ImportError:return
        with fitz.open(path) as pdf:
            self.assertGreater(len(pdf),1)
            self.assertTrue(all('TEST' not in page.get_text() for page in pdf))
            self.assertIn('Category119',''.join(page.get_text() for page in pdf))
        path=Path(self.temp.name)/'empty.pdf'
        export_report_pdf(self.db,'Empty','SELECT name FROM customers WHERE 1=0',path)
        with fitz.open(path) as pdf:self.assertIn('No records',pdf[0].get_text())


class GuiTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        import core_v1
        with patch.object(core_v1,'DB',Path(self.temp.name)/'test.db'):self.db=connect()
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO users(username,password,role) VALUES('admin','ignored','admin')")
            self.db.execute("INSERT INTO customers(name) VALUES('Customer A')")
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty) VALUES('P1','Sample product',2100,1000,30)")
        self.root=tk.Tk()
        self.root.geometry('1200x710')
        self.root.withdraw()
        from modern_theme import apply
        apply(self.root)
        self.app=BusinessDesk.__new__(BusinessDesk)
        self.app.root=self.root;self.app.db=self.db;self.app.user={'id':1,'username':'admin','role':'admin'};self.app._update_checked=True
        self.app.home()
        self.root.deiconify();self.root.update()
    def tearDown(self):
        self.root.destroy();self.db.close();self.temp.cleanup()
    @staticmethod
    def buttons(widget):
        for child in widget.winfo_children():
            if isinstance(child,ttk.Button):yield child
            yield from GuiTests.buttons(child)
    @staticmethod
    def widgets(widget,wclass):
        for child in widget.winfo_children():
            if isinstance(child,wclass):yield child
            yield from GuiTests.widgets(child,wclass)
    def tab(self,name):
        return self.app.tabs.nametowidget(next(tab for tab in self.app.tabs.tabs() if self.app._full_tab_labels[tab]==name))

    def test_narrow_tabs_admin_settings_are_visible(self):
        self.root.geometry('845x560');self.root.update()
        labels=[self.app.tabs.tab(t,'text') for t in self.app.tabs.tabs()]
        self.assertIn('Settings',labels)
        self.assertIn('Est. / Inv.',labels)
        for tabname in ('Admin','Settings / Updates'):
            tab=self.tab(tabname)
            for bar in self.widgets(tab, __import__('responsive_ui').ResponsiveToolbar):
                self.root.update()
                buttons=list(self.buttons(bar))
                if not buttons:continue
                self.assertGreater(bar.winfo_width(),100)
                for button in buttons:
                    self.assertEqual(button.winfo_manager(),'grid')
                    self.assertLessEqual(button.winfo_x()+button.winfo_width(),bar.winfo_width()+3,
                        f'{tabname}: {button.cget("text")} is clipped')
            self.assertTrue(any(isinstance(w,tk.Canvas) for w in self.widgets(tab,tk.Canvas)))

    def test_save_estimate_button_visible_and_return_selected_line(self):
        # Poll the dialog while the nested wait_window is running.
        def interact():
            modal=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
            modal.geometry('735x500');self.root.update()
            save=next(b for b in self.buttons(modal) if b.cget('text')=='Save Estimate')
            self.assertGreater(save.winfo_y(),0)
            self.assertLessEqual(save.winfo_rooty()+save.winfo_height(),modal.winfo_rooty()+modal.winfo_height())
            trees=list(self.widgets(modal,ttk.Treeview))
            self.assertEqual(len(trees),2)
            products=trees[0]
            products.selection_set(products.get_children()[0])
            products.event_generate('<<TreeviewSelect>>')
            modal.update()
            add=next(b for b in self.buttons(modal) if b.cget('text')=='Add product')
            add.invoke()
            save.invoke()
        self.root.after(180,interact)
        lines=self.app.select_document_products('Estimate',1)
        self.assertEqual(lines,[(1,'Sample product',1,2100,2100)])

    def test_save_estimate_end_to_end(self):
        """Confirm that the visible Save action persists a new estimate."""
        def submit_header():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
            button=next(b for b in self.buttons(dialog) if b.cget('text')=='Continue to products')
            button.invoke()
        def submit_products():
            dialog=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
            trees=list(self.widgets(dialog,ttk.Treeview))
            self.assertEqual(len(trees),2)
            tree=trees[0]
            tree.selection_set(tree.get_children()[0]);tree.event_generate('<<TreeviewSelect>>')
            dialog.update()
            next(b for b in self.buttons(dialog) if b.cget('text')=='Add product').invoke()
            next(b for b in self.buttons(dialog) if b.cget('text')=='Save Estimate').invoke()
        self.root.after(120,submit_header)
        self.root.after(380,submit_products)
        create=self.app._home_actions['estimate.new'][0]
        with patch('core_v1.messagebox.askyesno',return_value=True):
            create()
        row=self.db.execute("SELECT kind,subtotal,total FROM documents ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(tuple(row),('Estimate',2100,2100))

    def test_customer_form_has_separate_address_boxes(self):
        def interact():
            modal=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel))
            modal.update()
            labels=[w.cget('text') for w in self.widgets(modal,ttk.Label)]
            for name in ('Street address','City','State','ZIP / Postal code'):
                self.assertIn(name,labels)
            entries=list(self.widgets(modal,ttk.Entry))
            for item,value in zip(entries,('Customer B','b@example.com','555','55 Main','Watertown','WI','53094','Note')):
                item.delete(0,'end');item.insert(0,value)
            next(b for b in self.buttons(modal) if b.cget('text')=='Save customer').invoke()
        self.root.after(160,interact)
        selected=self.tab('Customers')
        self.app.tabs.select(selected)
        add=next(b for b in self.buttons(selected) if b.cget('text')=='Add customer')
        add.invoke()
        record=self.db.execute("SELECT city,state,zip_code FROM customers WHERE name='Customer B'").fetchone()
        self.assertEqual(tuple(record),('Watertown','WI','53094'))

    def test_flow_routing_orthogonal(self):
        home=self.tab('Home')
        canvases=list(self.widgets(home,tk.Canvas))
        canvas=max(canvases,key=lambda c:len(c.find_all()))
        conn=[i for i in canvas.find_all() if 'workflow_connector' in canvas.gettags(i) and canvas.type(i)=='line']
        self.assertGreaterEqual(len(conn),10)
        for item in conn:
            p=canvas.coords(item)
            self.assertTrue(p[0]==p[2] or p[1]==p[3],f'Non-orthogonal line: {p}')


if __name__=='__main__':main(verbosity=2)
