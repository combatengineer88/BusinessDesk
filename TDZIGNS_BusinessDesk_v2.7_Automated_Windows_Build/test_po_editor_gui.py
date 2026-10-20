"""Optional graphical PO workflow tests; run with a display or via xvfb-run."""
import os
import tempfile
import unittest
from unittest.mock import patch
import tkinter as tk

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='bd_po_gui_')
from modern_theme import apply
from po_editor import PurchaseOrderEditor
from businessdesk import schema
from core_v1 import connect
from pathlib import Path


class PurchaseOrderGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('core_v1.DB',Path(self.tmp.name)/'business.db'):
            self.db=connect()
        schema(self.db)
        self.db.execute("INSERT INTO suppliers(id,name) VALUES(1,'ACME Wholesale')")
        self.db.execute("INSERT INTO products(id,sku,name,price,cost,qty,supplier_id) VALUES(1,'A1','Product One',1800,675,20,1)")
        self.db.commit()
        self.root=tk.Tk()
        apply(self.root)
        self.root.geometry('1100x720')
        self.root.update()

    def tearDown(self):
        for child in self.root.winfo_children():
            if isinstance(child,tk.Toplevel):child.destroy()
        self.root.destroy()
        self.db.close()
        self.tmp.cleanup()

    def open_editor(self,po_id=None):
        with patch.object(tk.Toplevel,'wait_window',lambda *args,**kwargs:None):
            editor=PurchaseOrderEditor(self.root,self.db,po_id=po_id)
        editor.window.update_idletasks()
        return editor

    def test_create_save_button_stays_visible_and_saves(self):
        editor=self.open_editor()
        self.assertEqual(editor.save_button.cget('text'),'Save Purchase Order')
        editor.window.geometry('800x490')
        editor.window.update()
        button=editor.save_button
        self.assertTrue(button.winfo_ismapped())
        self.assertLess(button.winfo_rooty()+button.winfo_height(),editor.window.winfo_rooty()+editor.window.winfo_height()+2)
        editor.supplier_select.current(0);editor.supplier_changed()
        editor.product_select.current(0);editor.product_changed()
        editor.quantity.set('3');editor.unit_cost.set('7.25');editor.add_product()
        self.assertEqual(editor.order_total.cget('text'),'Order total: $21.75')
        editor.table.selection_set('1')
        editor.quantity.set('4');editor.unit_cost.set('8.00');editor.update_selected()
        self.assertEqual(editor.order_total.cget('text'),'Order total: $32.00')
        editor.notes.insert('1.0','Order by next Tuesday')
        editor.save()
        self.assertIsNotNone(editor.saved_id)
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders').fetchone()[0],3200)
        self.assertEqual(tuple(self.db.execute('SELECT qty,unit_cost FROM po_items').fetchone()),(4,800))

    def test_edit_existing_lines_and_save(self):
        from supplier_catalog import create_supplier_po
        po=create_supplier_po(self.db,1,'Old',[(1,2,675)])
        editor=self.open_editor(po)
        self.assertEqual(editor.save_button.cget('text'),'Save Changes')
        self.assertEqual(str(editor.supplier_select.cget('state')),'disabled')
        editor.table.selection_set('1')
        editor.quantity.set('7');editor.unit_cost.set('7.15')
        editor.update_selected()
        editor.notes.delete('1.0','end');editor.notes.insert('1.0','Revised')
        editor.save()
        self.assertEqual(self.db.execute('SELECT total FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],5005)
        self.assertEqual(self.db.execute('SELECT notes FROM purchase_orders WHERE id=?',(po,)).fetchone()[0],'Revised')

    def test_cancel_does_not_save(self):
        editor=self.open_editor()
        editor.supplier_select.current(0);editor.supplier_changed()
        editor.product_select.current(0);editor.product_changed()
        editor.add_product()
        editor.cancel()
        self.assertIsNone(editor.saved_id)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)


if __name__=='__main__':unittest.main(verbosity=2)
