"""Configurable PDF templates for estimates, invoices, and purchase orders.

Template settings are stored in the existing SQLite settings table. This module
never changes document rows, totals, accounting entries, or customer prices.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

KINDS = ('Estimate', 'Invoice', 'PO')
LAYOUTS = ('Classic', 'Modern', 'Compact')
FONTS = ('Helvetica', 'Times-Roman', 'Courier')
PAGE_SIZES = ('Letter', 'A4')
LOGO_POSITIONS = ('Left', 'Center', 'Right')
TEMPLATE_FIELDS = {
    'layout': 'Classic',
    'accent_color': '#183653',
    'font': 'Helvetica',
    'page_size': 'Letter',
    'logo_position': 'Left',
    'show_logo': True,
    'show_contact': True,
    'show_address': True,
    'show_notes': True,
    'show_zero_tax': True,
    'show_page_numbers': True,
    'heading': '',
    'tagline': '',
    'recipient_label': '',
    'notes_heading': 'Notes',
    'terms_heading': 'Terms & Conditions',
    'terms': '',
    'footer': '',
    'label_item': '',
    'label_quantity': 'Quantity',
    'label_rate': '',
    'label_total': 'Line total',
}
TEXT_FIELDS = tuple(k for k,v in TEMPLATE_FIELDS.items() if isinstance(v,str) and k not in ('layout','accent_color','font','page_size','logo_position'))
CHECK_FIELDS = tuple(k for k,v in TEMPLATE_FIELDS.items() if isinstance(v,bool))


def template_key(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError('Unknown document template: '+str(kind))
    return f'document_template_{kind.lower()}'


def defaults(kind: str) -> dict:
    template_key(kind)
    config = copy.deepcopy(TEMPLATE_FIELDS)
    config['heading'] = {'Estimate':'ESTIMATE', 'Invoice':'INVOICE', 'PO':'PURCHASE ORDER'}[kind]
    config['recipient_label'] = 'Supplier' if kind == 'PO' else 'Customer'
    config['label_item'] = 'Product' if kind == 'PO' else 'Item'
    config['label_rate'] = 'Unit cost' if kind == 'PO' else 'Unit price'
    return config


def validate(kind: str, config: dict) -> dict:
    """Reject bad settings rather than injecting untrusted XML/HTML into PDFs."""
    result = defaults(kind)
    if not isinstance(config, dict):
        raise ValueError('Document template must be an object')
    unknown = set(config) - set(TEMPLATE_FIELDS)
    if unknown:
        raise ValueError('Unknown template setting(s): '+', '.join(sorted(unknown)))
    for key, value in config.items():
        if key in CHECK_FIELDS:
            if type(value) is not bool:
                raise ValueError(f'{key} must be enabled or disabled')
        elif not isinstance(value,str):
            raise ValueError(f'{key} must be text')
        elif len(value) > (1400 if key in ('terms','footer') else 130):
            raise ValueError(f'{key} is too long')
        elif any(ord(c)<32 and c not in '\n\t' for c in value):
            raise ValueError(f'{key} includes a control character')
        result[key] = value
    for key,choices in [('layout',LAYOUTS),('font',FONTS),('page_size',PAGE_SIZES),('logo_position',LOGO_POSITIONS)]:
        if result[key] not in choices:
            raise ValueError(f'Invalid {key}: {result[key]}')
    if not re.fullmatch('#[0-9a-fA-F]{6}',result['accent_color']):
        raise ValueError('Accent color must use #RRGGBB, e.g. #183653')
    return result


def load_template(db, kind: str) -> dict:
    row = db.execute('SELECT value FROM settings WHERE key=?',(template_key(kind),)).fetchone()
    if not row:
        return defaults(kind)
    try:
        return validate(kind,json.loads(row[0]))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError(f'Saved {kind} template is invalid. Reset its settings. Details: {exc}') from exc


def save_template(db, kind: str, config: dict) -> None:
    value = json.dumps(validate(kind,config),ensure_ascii=False)
    with db:
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(template_key(kind),value))


def reset_template(db, kind: str) -> None:
    with db:
        db.execute('DELETE FROM settings WHERE key=?',(template_key(kind),))


def _settings(db):
    return {row['key']: row['value'] for row in db.execute('SELECT key,value FROM settings')}


def render_document(db, kind: str, record_id: int, output, template_override=None, preview=False):
    """Render saved records or preview data. Monetary totals always come from saved rows."""
    from address_utils import customer_address
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
    from reportlab.lib.utils import ImageReader

    conf = validate(kind,template_override) if template_override is not None else load_template(db,kind)
    company = _settings(db)
    accent = colors.HexColor(conf['accent_color'])
    page_size = letter if conf['page_size']=='Letter' else A4
    compact = conf['layout']=='Compact'
    margin = 30 if compact else 42
    usable = page_size[0]-2*margin
    font = conf['font']
    bold = {'Helvetica':'Helvetica-Bold','Times-Roman':'Times-Bold','Courier':'Courier-Bold'}[font]
    base_size = 9 if compact else 10
    para_style = ParagraphStyle('bd_text',fontName=font,fontSize=base_size,leading=base_size+4,spaceAfter=4)
    small_style = ParagraphStyle('bd_small',parent=para_style,fontSize=8.5,leading=12)
    heading_style=ParagraphStyle('bd_heading',parent=para_style,fontName=bold,fontSize=18 if compact else 23,leading=27,textColor=accent,spaceAfter=10)
    company_style=ParagraphStyle('bd_company',parent=para_style,fontName=bold,fontSize=16 if compact else 20,leading=24,spaceAfter=4)
    right_style=ParagraphStyle('bd_right',parent=para_style,alignment=TA_RIGHT)

    def p(text,style=para_style):
        return Paragraph(escape(str(text if text is not None else '')).replace('\n','<br/>'),style)
    def dollar(amount):return f'${int(amount)/100:,.2f}'

    if preview:
        metadata={
            'name':'Sample Supplier Company' if kind=='PO' else 'Sample Customer',
            'address':'123 Example Street\nSample City, WI 53000',
            'email':'sample@example.com',
            'date':'2026-01-15',
            'notes':'These are sample document details, not business records.',
            'subtotal':5800,'tax':0 if kind=='PO' else 319,
            'total':5800 if kind=='PO' else 6119,
            'rows':[('Sample Product A',2,1500,3000),('Sample Product B',4,700,2800)],
            'number':'PREVIEW',
        }
    elif kind=='PO':
        doc=db.execute('''SELECT p.*,s.name,s.address,s.email FROM purchase_orders p
                          JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?''',(record_id,)).fetchone()
        if not doc:raise ValueError('Purchase order not found')
        items=db.execute('''SELECT i.qty,i.unit_cost,p.name FROM po_items i
                            JOIN products p ON p.id=i.product_id WHERE i.po_id=? ORDER BY i.id''',(record_id,)).fetchall()
        metadata={'name':doc['name'],'address':doc['address'],'email':doc['email'],
                  'date':doc['ordered_on'],'notes':doc['notes'],'subtotal':doc['total'],
                  'tax':0,'total':doc['total'],'number':record_id,
                  'rows':[(r['name'],r['qty'],r['unit_cost'],r['qty']*r['unit_cost']) for r in items]}
    else:
        postal=',c.city,c.state,c.zip_code' if {'city','state','zip_code'} <= {r[1] for r in db.execute('PRAGMA table_info(customers)')} else ",' ' AS city,' ' AS state,' ' AS zip_code"
        doc=db.execute(f'''SELECT d.*,c.name,c.address,c.email,{postal.lstrip(',')} FROM documents d
                          JOIN customers c ON c.id=d.customer_id WHERE d.id=?''',(record_id,)).fetchone()
        if not doc:raise ValueError('Document not found')
        if doc['kind']!=kind:raise ValueError('Document type mismatch')
        items=db.execute('''SELECT description,qty,unit_price,line_total FROM document_items
                            WHERE document_id=? ORDER BY id''',(record_id,)).fetchall()
        metadata={'name':doc['name'],'address':customer_address(doc['address'],doc['city'],doc['state'],doc['zip_code']),'email':doc['email'],
                  'date':doc['created'],'notes':doc['notes'],'subtotal':doc['subtotal'],
                  'tax':doc['tax'],'total':doc['total'],'number':record_id,
                  'rows':[(r['description'],r['qty'],r['unit_price'],r['line_total']) for r in items]}

    story=[]
    if conf['show_logo']:
        logo=company.get('logo_path','')
        if logo and Path(logo).is_file():
            try:
                image=ImageReader(logo)
                width,height=image.getSize()
                scale=min(1,190/width,77/height)
                img=Image(logo,width=width*scale,height=height*scale)
                pos={'Left':'LEFT','Center':'CENTER','Right':'RIGHT'}[conf['logo_position']]
                img.hAlign=pos
                story.extend([img,Spacer(1,8 if compact else 12)])
            except (OSError,ValueError):pass

    company_name = company.get('business_name') or 'TDZIGNS LLC'
    if conf['layout']=='Modern':
        heading=p(company_name,ParagraphStyle('modern_company',parent=company_style,textColor=colors.white))
        modern=Table([[heading]],colWidths=[usable])
        modern.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),accent),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.extend([modern,Spacer(1,10)])
    else:
        story.append(p(company_name,company_style))
    if conf['show_contact']:
        for key in ('business_address','business_phone','business_email'):
            if company.get(key):story.append(p(company[key],small_style))
    story.append(Spacer(1,7 if compact else 16))

    display_title=(conf['heading'].strip() or {'Estimate':'ESTIMATE','Invoice':'INVOICE','PO':'PURCHASE ORDER'}[kind])
    if conf['layout']=='Modern':
        title_style=ParagraphStyle('modern_title',parent=heading_style,textColor=accent)
    else:title_style=heading_style
    # Group the document reference beside its date, not in the page title.
    # The same placement is used for estimates, invoices, and purchase orders.
    story.append(p(display_title,title_style))
    if conf['tagline'].strip():story.append(p(conf['tagline'],small_style))
    recipient=[p(f'{conf["recipient_label"]}: {metadata["name"]}')]
    if conf['show_address'] and metadata.get('address'):
        recipient.append(p(metadata['address'],small_style))
    reference_label={'Estimate':'Estimate #','Invoice':'Invoice #','PO':'PO #'}[kind]
    detail_heading=ParagraphStyle('bd_detail_heading',parent=small_style,fontName=bold,textColor=accent)
    details=[p('DOCUMENT DETAILS',detail_heading),
             p(f'{reference_label}: {metadata["number"]}',small_style),
             p(f'Date: {metadata["date"]}',small_style)]
    if not preview and kind=='Invoice' and 'credit_due_on' in doc.keys() and doc['credit_due_on']:
        details.append(p(f'Credit account due: {doc["credit_due_on"]}',small_style))
    meta=Table([[recipient,details]],colWidths=[usable*0.59,usable*0.41],hAlign='LEFT')
    meta.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(0,0),15),
        ('LEFTPADDING',(1,0),(1,0),10),('RIGHTPADDING',(1,0),(1,0),0),
        ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    story.append(meta)
    story.append(Spacer(1,10 if compact else 16))

    head=[conf['label_item'],conf['label_quantity'],conf['label_rate'],conf['label_total']]
    rows=[[p(h,ParagraphStyle('bd_colhead_'+str(i),parent=small_style,fontName=bold,textColor=colors.white)) for i,h in enumerate(head)]]
    for title,quantity,unit,linetotal in metadata['rows']:
        rows.append([p(title),str(quantity),dollar(unit),dollar(linetotal)])
    col_widths=[usable*0.49,usable*0.13,usable*0.18,usable*0.20]
    table=Table(rows,colWidths=col_widths,repeatRows=1,hAlign='LEFT')
    padding=5 if compact else 9
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),accent),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F0F3F7')]),
        ('TEXTCOLOR',(0,1),(-1,-1),colors.HexColor('#222222')),
        ('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,-1),(-1,-1),0.5,colors.HexColor('#D1D5DB')),
        ('ALIGN',(1,1),(-1,-1),'RIGHT')]))
    story.extend([table,Spacer(1,12)])

    totals=[('Subtotal',metadata['subtotal'])]
    if kind!='PO' and (metadata['tax'] or conf['show_zero_tax']):totals.append(('Tax',metadata['tax']))
    totals.append(('TOTAL',metadata['total']))
    total_sty=ParagraphStyle('bd_total',parent=right_style,fontName=bold,fontSize=11 if compact else 12,textColor=accent)
    for label,value in totals:
        style=total_sty if label=='TOTAL' else right_style
        story.append(p(f'{label}: {dollar(value)}',style))
    if conf['show_notes'] and metadata.get('notes'):
        story.extend([Spacer(1,12),p(conf['notes_heading'],ParagraphStyle('bd_note_head',parent=para_style,fontName=bold)),p(metadata['notes'])])
    if conf['terms'].strip():
        story.extend([Spacer(1,12),p(conf['terms_heading'],ParagraphStyle('bd_terms_head',parent=para_style,fontName=bold)),p(conf['terms'])])

    # Footer is repeated on each page and does not modify monetary line items.
    def draw_footer(canvas, doc):
        canvas.saveState()
        width,height=page_size
        if preview:
            canvas.setFillColor(colors.HexColor('#CFD5DE'))
            canvas.setFont(bold,35)
            canvas.translate(width/2,height/2)
            canvas.rotate(40)
            canvas.drawCentredString(0,0,'SAMPLE PREVIEW')
            canvas.rotate(-40)
            canvas.translate(-width/2,-height/2)
        canvas.setFillColor(accent)
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.7)
        canvas.line(margin,36,width-margin,36)
        footer=(conf['footer'] or '').replace('\n',' ')
        # Limit footer draw width to keep long user content inside page.
        footer=footer[:120]
        if footer:
            canvas.setFont(font,8)
            canvas.drawString(margin,23,footer[:int(usable/4.5)])
        if conf['show_page_numbers']:
            canvas.setFont(font,8)
            canvas.drawRightString(width-margin,23,'Page '+str(doc.page))
        canvas.restoreState()

    pdf=SimpleDocTemplate(str(output),pagesize=page_size,leftMargin=margin,rightMargin=margin,
                          topMargin=30 if compact else 38,bottomMargin=57,
                          title=f'{display_title} {metadata["number"]}',author=company_name)
    pdf.build(story,onFirstPage=draw_footer,onLaterPages=draw_footer)
    return Path(output)
