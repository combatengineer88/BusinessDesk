"""Source-only CSV tests; no desktop display or database required."""
import csv
import tempfile
import unittest
from pathlib import Path
from catalog_csv import export_catalog_view, catalog_view_rows, escape_spreadsheet_formula

class StubTree:
    def __init__(self):
        self.columns=('ID','SKU','Name','Price','Reorder Cost','Item Cost','Margin %',
                      'Image','Barcode PNG')
        self.data={
            'item1':(1,'ABC-48','Black T-Shirt','$12.99','$192.00','$4.00','69.2%','Yes','No'),
            'item2':(3,'MUG-12','=IMPORT(\"bad\")','$9.99','$90.00','$2.50','75.0%','No','Yes'),
        }
    def __getitem__(self,key):return self.columns if key=='columns' else None
    def heading(self,col,option):return col
    def get_children(self, parent=''):
        return ('item1',)   # visible / filtered row only
    def item(self,iid,option):return self.data[iid]

class CatalogCSVTests(unittest.TestCase):
    def test_matches_interface_columns_and_filtered_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.csv'
            count=export_catalog_view(StubTree(),path)
            self.assertEqual(count,1)
            with path.open(encoding='utf-8-sig',newline='') as handle:
                rows=list(csv.reader(handle))
            self.assertEqual(rows[0],list(StubTree().columns))
            self.assertEqual(rows[1],['1','ABC-48','Black T-Shirt','$12.99',
                '$192.00','$4.00','69.2%','Yes','No'])
            self.assertEqual(len(rows),2)
            self.assertNotIn('/Users/',path.read_text(encoding='utf-8-sig'))
    def test_formula_like_text_is_not_executable_when_opened_in_spreadsheets(self):
        for value in ['=SUM(1,1)','  +CMD','\t@IMPORT','-cmd']:
            self.assertTrue(escape_spreadsheet_formula(value).startswith("'"))
        self.assertEqual(escape_spreadsheet_formula('ABC-48'),'ABC-48')

if __name__=='__main__':unittest.main()
