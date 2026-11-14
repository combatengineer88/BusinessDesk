"""PhoenixLedger inventory edits, barcode PNG attachment and print-ready label sheets.

All sticker geometry uses PDF points (72/inch). Label output is intentionally
vector-based for generated Code 128 symbols, never a raster screenshot.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from PIL import Image
from reportlab.graphics.barcode import code128
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


LABEL_FORMATS = {
    'Avery 5160 / 8160 - 30 labels (2-5/8 x 1 in)': {
        'rows': 10, 'cols': 3, 'width': 2.625 * 72, 'height': 72,
        'left': 0.1875 * 72, 'top': 0.5 * 72,
        'x_pitch': 2.75 * 72, 'y_pitch': 72,
    },
    'Avery 5163 / 8163 - 10 labels (4 x 2 in)': {
        'rows': 5, 'cols': 2, 'width': 4 * 72, 'height': 2 * 72,
        'left': 0.15625 * 72, 'top': 0.5 * 72,
        'x_pitch': 4.1875 * 72, 'y_pitch': 2 * 72,
    },
}


EDITABLE = frozenset(('sku', 'barcode', 'name', 'description', 'price', 'cost', 'qty', 'supplier_id'))


def ensure_inventory_schema(db):
    """Upgrade an existing products table without modifying existing stock/links."""
    cols = {r[1] for r in db.execute('PRAGMA table_info(products)')}
    if 'barcode_image_path' not in cols:
        db.execute("ALTER TABLE products ADD COLUMN barcode_image_path TEXT DEFAULT ''")
    db.commit()


def edit_product_field(db, product_id, field, entered):
    """Validate and save a single spreadsheet-style cell, without rewriting other columns."""
    if field not in EDITABLE:
        raise ValueError('This product column cannot be edited inline.')
    if not db.execute('SELECT 1 FROM products WHERE id=?', (product_id,)).fetchone():
        raise ValueError('The product no longer exists.')
    if field in ('price', 'cost'):
        from core_v1 import cents
        value = cents(entered)
    elif field == 'qty':
        stripped = str(entered).strip()
        if not stripped or not stripped.isdecimal():
            raise ValueError('Stock must be a whole number of units (zero or more).')
        value = int(stripped)
    elif field == 'supplier_id':
        if entered in (None, '', 'Unassigned'):
            value = None
        else:
            try:
                value = int(entered)
            except (TypeError, ValueError) as ex:
                raise ValueError('Choose a supplier from the list.') from ex
            if not db.execute('SELECT 1 FROM suppliers WHERE id=?',(value,)).fetchone():
                raise ValueError('The selected supplier no longer exists.')
    else:
        value = str(entered).strip()
        if field in ('sku', 'name') and not value:
            raise ValueError(f'{field.upper() if field == "sku" else "Product name"} is required.')
    with db:
        db.execute(f'UPDATE products SET {field}=? WHERE id=?', (value, product_id))
    return value


def _check_png(file):
    file = Path(file)
    if file.suffix.lower() != '.png' or not file.is_file():
        raise ValueError('Choose a .png barcode image.')
    if file.stat().st_size > 12_000_000:
        raise ValueError('Barcode image is too large (12 MB maximum).')
    try:
        with Image.open(file) as img:
            if img.format != 'PNG':
                raise ValueError('The selected file does not contain a PNG image.')
            if img.width < 40 or img.height < 15 or img.width > 12000 or img.height > 12000:
                raise ValueError('Barcode PNG dimensions are invalid or too small.')
            img.verify()
    except (OSError, SyntaxError) as ex:
        raise ValueError('The barcode PNG could not be read.') from ex
    return file


def attach_barcode_png(db, product_id, png_file, data_dir):
    """Copy a selected barcode to app-managed storage, then link only that product."""
    if not db.execute('SELECT 1 FROM products WHERE id=?', (product_id,)).fetchone():
        raise ValueError('Select a product that still exists.')
    original = _check_png(png_file)
    folder = Path(data_dir) / 'barcode_images'
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f'barcode_{product_id}_{uuid4().hex[:12]}.png'
    try:
        shutil.copy2(original, destination)
        _check_png(destination)
        with db:
            db.execute('UPDATE products SET barcode_image_path=? WHERE id=?',
                       (str(destination), product_id))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def get_label_products(db, selection):
    """Return an ordered, validated list with qty copies per selected product."""
    result = []
    total = 0
    for product_id, quantity in selection:
        quantity = int(quantity)
        if not 1 <= quantity <= 500:
            raise ValueError('Choose between 1 and 500 stickers per product.')
        total += quantity
        if total > 3000:
            raise ValueError('You can print at most 3,000 stickers in one batch.')
        row = db.execute('SELECT id, sku, barcode, name, price, barcode_image_path '
                         'FROM products WHERE id=?', (product_id,)).fetchone()
        if row is None:
            raise ValueError(f'Product #{product_id} no longer exists.')
        data = dict(row)
        png = data.get('barcode_image_path') or ''
        if png and Path(png).is_file():
            _check_png(png)
            data['source'] = 'PNG'
        else:
            fallback = str(data.get('barcode') or data['sku']).strip()
            if not fallback or any(ord(c) < 32 or ord(c) > 126 for c in fallback):
                raise ValueError(f"Product '{data['name']}' needs a valid ASCII barcode/SKU or attached PNG.")
            data['source'] = 'Code128'
        result.append((data, quantity))
    if not result:
        raise ValueError('Select at least one product.')
    return result


def _fit_text(pdf, s, max_width, size=8, minimum=5):
    s = str(s).strip().replace('\n', ' ')
    while size > minimum and pdf.stringWidth(s, 'Helvetica', size) > max_width:
        size -= 0.5
    if pdf.stringWidth(s, 'Helvetica', size) > max_width:
        while s and pdf.stringWidth(s + '...', 'Helvetica', size) > max_width:
            s = s[:-1]
        s += '...'
    return s, size


def _draw_one(pdf, product, x, y, width, height, print_price):
    """Draw inside clip rectangle; all printed features stay inside the sticker."""
    pdf.saveState()
    clip = pdf.beginPath()
    clip.rect(x + 3, y + 3, width - 6, height - 6)
    pdf.clipPath(clip, stroke=0, fill=0)
    wide = height >= 120
    pad = 9 if wide else 5
    text_w = width - 2 * pad
    left = x + pad
    name_size = 11 if wide else 8
    title, name_size = _fit_text(pdf, product['name'], text_w, name_size, 6)
    pdf.setFillColorRGB(0.08, 0.14, 0.22)
    pdf.setFont('Helvetica-Bold', name_size)
    pdf.drawString(left, y + height - pad - name_size, title)

    price_part = f"    ${product['price'] / 100:,.2f}" if print_price else ''
    descriptor = 'SKU: ' + str(product['sku']) + price_part
    small, fs = _fit_text(pdf, descriptor, text_w, 7.5 if wide else 6.6, 5)
    pdf.setFont('Helvetica', fs)
    pdf.drawString(left, y + pad + 1, small)

    bottom = y + pad + 12
    top = y + height - pad - name_size - 5
    available_h = max(10, top - bottom)
    attached = (product.get('barcode_image_path') or '').strip()
    if attached and Path(attached).is_file():
        with Image.open(attached) as img:
            src_w, src_h = img.size
        scale = min(text_w / src_w, available_h / src_h)
        draw_w, draw_h = src_w * scale, src_h * scale
        pdf.drawImage(ImageReader(attached), x + (width - draw_w) / 2,
                      bottom + (available_h - draw_h) / 2,
                      draw_w, draw_h, mask='auto')
    else:
        value = str(product.get('barcode') or product['sku']).strip()
        # Give Code 128 a readable physical x-dimension, with human-readable
        # contents immediately below the bars for manual confirmation.
        symbol = code128.Code128(value, barHeight=max(12, available_h - 10),
                                barWidth=0.85 if wide else 0.72, humanReadable=False)
        scale = min(1, text_w / symbol.width, (available_h - 10) / symbol.height)
        pdf.saveState()
        pdf.translate(x + (width - symbol.width * scale) / 2,
                      bottom + 10 + (available_h - 10 - symbol.height * scale) / 2)
        pdf.scale(scale, scale)
        symbol.drawOn(pdf, 0, 0)
        pdf.restoreState()
        number, number_size = _fit_text(pdf, value, text_w, 6.5, 5)
        pdf.setFont('Helvetica', number_size)
        pdf.drawCentredString(x + width / 2, bottom + 1, number)
    pdf.restoreState()


def render_label_sheet(db, selection, output, format_name=None, start_at=1, print_price=True):
    """Render selected products to US Letter PDF with real label-sheet positioning.

    start_at is a 1-based sticker position on the first page, for partially used sheets.
    PDF viewer/printer must use **Actual Size / 100%**, never Fit-to-page.
    """
    format_name = format_name or next(iter(LABEL_FORMATS))
    if format_name not in LABEL_FORMATS:
        raise ValueError('Choose a supported label-sheet format.')
    fmt = LABEL_FORMATS[format_name]
    slots = fmt['rows'] * fmt['cols']
    if not 1 <= int(start_at) <= slots:
        raise ValueError(f'First label position must be between 1 and {slots}.')
    products = get_label_products(db, selection)
    stickers = [p for p, count in products for _ in range(count)]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.stem + '.staging_' + uuid4().hex[:8] + '.pdf')
    try:
        pdf = canvas.Canvas(str(tmp), pagesize=(612, 792), pageCompression=1)
        pdf.setTitle('PhoenixLedger - Product Barcode Stickers')
        pdf.setAuthor('PhoenixLedger')
        page_index = int(start_at) - 1
        for product in stickers:
            if page_index >= slots:
                pdf.showPage()
                page_index = 0
            row, col = divmod(page_index, fmt['cols'])
            x = fmt['left'] + col * fmt['x_pitch']
            y = 792 - fmt['top'] - row * fmt['y_pitch'] - fmt['height']
            _draw_one(pdf, product, x, y, fmt['width'], fmt['height'], print_price)
            page_index += 1
        pdf.save()
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    return output
