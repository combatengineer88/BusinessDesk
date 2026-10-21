"""Regression tests for v2.9.11 Home workflow and direct shortcuts.

The GUI tests run under Xvfb on Linux and under interactive Windows desktop.
"""
import sqlite3
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest import TestCase, main
from unittest.mock import patch

from core_v1 import connect
from businessdesk import PhoenixLedger, schema
from home_workspace import QUICK_LINKS, SUPPLY_FLOW, CUSTOMER_FLOW, HomeWorkspace


class HomeTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        # core_v1 connect() initializes the complete v1 database schema.
        original=__import__('core_v1')
        with patch.object(original,'DB',__import__('pathlib').Path(self.folder.name)/'testing.db'):
            from core_v1 import connect as make_db
            old=self.db
            self.db=make_db()
            old.close()
        schema(self.db)
        with self.db:
            self.db.execute("INSERT INTO users(username,password,role) VALUES('owner','unused','admin')")
            self.db.execute("INSERT INTO suppliers(name) VALUES('Sample supplier')")
            self.db.execute("INSERT INTO customers(name) VALUES('Sample customer')")
            self.db.execute("INSERT INTO products(sku,name,price,cost,qty,supplier_id) VALUES('P100','Product',1200,400,12,1)")
        self.root=tk.Tk();self.root.geometry('1280x800')
        self.root.withdraw()
        self.app=PhoenixLedger.__new__(PhoenixLedger)
        self.app.root=self.root
        self.app.db=self.db
        self.app.user={'username':'owner','role':'admin','id':1}
        self.app._update_checked=True
        self.app.home()
        self.root.deiconify();self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.db.close()
        self.folder.cleanup()

    def tab_names(self):
        return [self.app.tabs.tab(tab,'text') for tab in self.app.tabs.tabs()]

    def find_button(self,widget,text):
        if isinstance(widget,ttk.Button) and widget.cget('text')==text:return widget
        for child in widget.winfo_children():
            found=self.find_button(child,text)
            if found:return found
        return None

    def test_home_starts_first_and_preserves_other_tabs(self):
        tabs=self.tab_names()
        self.assertEqual(tabs[0],'Home')
        self.assertIn('Purchase Orders',tabs)
        self.assertIn('Settings / Updates',tabs)
        self.assertEqual(self.app.tabs.tab(self.app.tabs.select(),'text'),'Home')
        self.assertIsNotNone(self.find_button(self.app.tabs,'Add supplier'))
        self.assertIsNotNone(self.find_button(self.app.tabs,'Create new estimate'))
        self.assertIsNotNone(self.find_button(self.app.tabs,'Visual template designer'))
        self.assertIsNotNone(self.find_button(self.app.tabs,'Import products from Excel'))

    def test_home_lanes_and_workflow_actions(self):
        home_tab=self.app.tabs.nametowidget(self.app.tabs.tabs()[0])
        workspace=next(w for w in home_tab.winfo_children()[0].winfo_children() if isinstance(w,ttk.Frame))
        # Find rendered flow-canvas and inspect node tags and text.
        def canvases(widget):
            for child in widget.winfo_children():
                if isinstance(child,tk.Canvas):yield child
                yield from canvases(child)
        found=list(canvases(home_tab))
        self.assertGreaterEqual(len(found),2)
        flow=max(found,key=lambda c:len(c.find_all()))
        rendered=' '.join(str(flow.itemcget(item,'text')) for item in flow.find_all() if flow.type(item)=='text')
        self.assertIn('SUPPLIER / SUPPLY CHAIN',rendered)
        self.assertIn('CUSTOMER / SALES CHAIN',rendered)
        self.assertIn('Receive full',rendered)
        self.assertIn('Partial receipt',rendered)
        self.assertIn('Create an',rendered)
        all_tags={tag for item in flow.find_all() for tag in flow.gettags(item)}
        self.assertIn('action:po.new',all_tags)
        self.assertIn('action:estimate.new',all_tags)
        self.assertIn('action:po.partial',all_tags)
        self.assertIn('action:supplier.payment',all_tags)
        self.assertIn('action:customer.credit',all_tags)

    def test_supplier_add_shortcut_opens_real_action(self):
        with patch.object(self.app,'form',return_value={'name':'New vendor','email':'','phone':'','address':''}):
            with patch('businessdesk.messagebox.showinfo'):
                self.app.navigate_home_action('supplier.add')
        self.assertEqual(self.db.execute("SELECT count(*) FROM suppliers WHERE name='New vendor'").fetchone()[0],1)
        self.assertEqual(self.app.tabs.tab(self.app.tabs.select(),'text'),'Purchase Orders')

    def test_existing_purchase_order_shortcut_selects_open_record(self):
        from supplier_catalog import create_supplier_po
        with self.db:
            po_id=create_supplier_po(self.db,1,'',[(1,3,400)])
        self.app.home()
        def choose_first(tree,action,selector):
            iid=next(iid for iid in tree.get_children('') if selector(tree.item(iid,'values')))
            tree.selection_set(iid)
            return True
        with patch.object(self.app,'_home_choose_record',side_effect=choose_first) as picker:
            with patch('businessdesk.open_purchase_order_editor',return_value=None) as editor:
                self.app.navigate_home_action('po.edit')
        self.assertTrue(picker.called)
        editor.assert_called_once()
        self.assertEqual(editor.call_args.kwargs['po_id'],po_id)
        self.assertEqual(self.app.tabs.tab(self.app.tabs.select(),'text'),'Purchase Orders')

    def test_receive_po_workflow_uses_existing_accounting_logic(self):
        from supplier_catalog import create_supplier_po
        po_id=create_supplier_po(self.db,1,'',[(1,2,400)])
        self.app.home()
        original_qty=self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0]
        def choose_first(tree,action,selector):
            iid=next(iid for iid in tree.get_children('') if selector(tree.item(iid,'values')))
            tree.selection_set(iid)
            return True
        with patch.object(self.app,'_home_choose_record',side_effect=choose_first):
            with patch('businessdesk.messagebox.askyesno',return_value=True),patch('businessdesk.messagebox.showinfo'):
                self.app.navigate_home_action('po.receive')
        self.assertEqual(self.db.execute('SELECT qty FROM products WHERE id=1').fetchone()[0],original_qty+2)
        self.assertEqual(self.db.execute('SELECT status FROM purchase_orders WHERE id=?',(po_id,)).fetchone()[0],'Received')
        self.assertEqual(self.db.execute('SELECT count(*) FROM journal WHERE source_type=? AND source_id=?',('po_receipt',1)).fetchone()[0],1)

    def test_customer_and_product_shortcuts(self):
        for action,tab in [('customer.add','Customers'),('customer.edit','Customers'),
                           ('product.add','Products'),('product.edit','Products'),
                           ('estimate.new','Estimates / Invoices'),('reports','Reports'),
                           ('accounting','Accounting'),('dashboard','Dashboard')]:
            self.assertIn(action,self.app._home_actions or {'x':None}) if action not in ('reports','accounting','dashboard') else None
            self.assertIn(tab,self.tab_names())
        self.assertEqual({link for _,items in QUICK_LINKS for _,link in items if link is not None}.issubset(
            set(self.app._home_actions)|{'dashboard','reports','accounting','admin','templates','settings'}),True)

    def test_saved_navigation_order_keeps_home_and_others(self):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('tab_order',?)",
                            ('["Customers", "Home", "Products"]',))
        self.app.home()
        self.assertEqual(self.tab_names()[:3],['Customers','Home','Products'])


if __name__=='__main__':main(verbosity=2)
