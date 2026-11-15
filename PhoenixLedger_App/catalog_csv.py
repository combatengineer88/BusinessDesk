"""Export the visible Products grid without leaking local media file paths.

CSV is a text data format: headers, cell text, and ordering follow the UI;
fonts, column widths, colors and rounded button styling cannot be embedded.
"""
import csv
from pathlib import Path


def escape_spreadsheet_formula(value):
    """Don't let imported product descriptions execute Excel formulas on open."""
    if value is None:
        return ''
    value = str(value)
    if value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def catalog_view_rows(tree):
    """Take exactly the ordered columns and filtered, visible rows in a Treeview."""
    columns=list(tree['columns'])
    headers=[str(tree.heading(col,'text') or col) for col in columns]
    rows=[]
    for iid in tree.get_children(''):
        values=list(tree.item(iid,'values'))
        rows.append([escape_spreadsheet_formula(value) for value in values])
    return headers,rows


def export_catalog_view(tree,path):
    headers,rows=catalog_view_rows(tree)
    with open(path,'w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)
