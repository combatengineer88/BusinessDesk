"""Regression tests for customer pricing and tax-exemption migrations."""
import sqlite3
import unittest
from decimal import Decimal, ROUND_HALF_UP
from businessdesk import schema

class PricingTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
           CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,email TEXT,phone TEXT,address TEXT,notes TEXT);
           CREATE TABLE products(id INTEGER PRIMARY KEY,sku TEXT,name TEXT,price INTEGER,cost INTEGER,qty INTEGER);
           CREATE TABLE documents(id INTEGER PRIMARY KEY,kind TEXT,customer_id INTEGER,created TEXT,status TEXT,subtotal INTEGER,tax INTEGER,total INTEGER,notes TEXT,created_by INTEGER);
           CREATE TABLE document_items(id INTEGER PRIMARY KEY,document_id INTEGER,product_id INTEGER,description TEXT,qty INTEGER,unit_price INTEGER,line_total INTEGER);
           CREATE TABLE payments(id INTEGER PRIMARY KEY,document_id INTEGER,paid_on TEXT,amount INTEGER,method TEXT);
           CREATE TABLE expenses(id INTEGER PRIMARY KEY,spent_on TEXT,category TEXT,vendor TEXT,description TEXT,amount INTEGER);
           CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,password TEXT,role TEXT);
        ''')
        self.db.execute("INSERT INTO customers(id,name) VALUES(1,'Customer A'),(2,'Customer B')")
        self.db.execute("INSERT INTO products(id,sku,name,price,cost,qty) VALUES(1,'P1','Shirt',2500,1000,20)")
        schema(self.db)
    def tearDown(self):self.db.close()
    def test_existing_customer_defaults_to_taxable(self):
        self.assertEqual([r['tax_exempt'] for r in self.db.execute('SELECT * FROM customers ORDER BY id')],[0,0])
    def test_customer_specific_price_and_fallback(self):
        self.db.execute('INSERT INTO customer_prices(customer_id,product_id,price) VALUES(2,1,1800)')
        sql='''SELECT coalesce(cp.price,p.price) AS price FROM products p LEFT JOIN customer_prices cp
          ON cp.product_id=p.id AND cp.customer_id=? WHERE p.id=1'''
        self.assertEqual(self.db.execute(sql,(1,)).fetchone()['price'],2500)
        self.assertEqual(self.db.execute(sql,(2,)).fetchone()['price'],1800)
    def test_price_migration_repeatable(self):
        schema(self.db)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM customer_prices').fetchone()[0],0)
    def test_exemption_and_tax_calculation(self):
        self.db.execute('UPDATE customers SET tax_exempt=1 WHERE id=2')
        tax=lambda cid,subtotal,rate: 0 if self.db.execute('SELECT tax_exempt FROM customers WHERE id=?',(cid,)).fetchone()[0] else int((Decimal(subtotal)*Decimal(rate)/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        self.assertEqual(tax(1,2500,'5.5'),138)
        self.assertEqual(tax(2,1800,'5.5'),0)
if __name__=='__main__':unittest.main()
