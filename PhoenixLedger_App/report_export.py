"""Branded multi-page PDF reports; read-only queries, no accounting mutations."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.sax.saxutils import escape

MONEY_COLUMNS = {'billed', 'received', 'spent', 'total', 'paid', 'balance', 'amount', 'debit', 'credit',
                 'ordered_total', 'received_value', 'unpaid_balance', 'credit_limit', 'outstanding'}


def format_report_cell(column, value):
    if value is None:return ''
    if column.casefold() in MONEY_COLUMNS:
        try:
            amount=Decimal(str(value))
            if amount.is_finite():return f'${amount:,.2f}'
        except (InvalidOperation,ValueError):pass
    return str(value)


def get_report_data(db, sql):
    """Read-only report data, fetched before rendering to avoid mutation."""
    if not sql.lstrip().upper().startswith('SELECT '):
        raise ValueError('PDF reports must use a read-only SELECT statement.')
    cursor=db.execute(sql)
    columns=[item[0] for item in cursor.description]
    rows=[tuple(format_report_cell(col,row[i]) for i,col in enumerate(columns)) for row in cursor]
    return columns,rows


def export_report_pdf(db, title, sql, output, *, when=None):
    from reportlab.platypus import SimpleDocTemplate, Table, LongTable, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth

    cols,rows=get_report_data(db,sql)
    if not cols:raise ValueError('Report has no columns.')
    settings={r['key']:r['value'] for r in db.execute('SELECT key,value FROM settings')}
    company=settings.get('business_name') or 'TDZIGNS LLC'
    address=settings.get('business_address','')
    phone=settings.get('business_phone','')
    email=settings.get('business_email','')
    logo_path=Path(settings['logo_path']) if settings.get('logo_path') else None
    stamp=when or datetime.now()
    # Landscape for financial reports with many columns; all reports use Letter pages.
    pagesize=landscape(letter) if len(cols)>=6 else letter
    w,h=pagesize
    left=43;right=43
    usable=w-left-right
    doc=SimpleDocTemplate(str(output),pagesize=pagesize,topMargin=152,bottomMargin=58,
                          leftMargin=left,rightMargin=right,title=f'{company} — {title}',author=company)
    primary=colors.HexColor('#1E3A5F')
    accent=colors.HexColor('#2563EB')
    ink=colors.HexColor('#253549')
    muted=colors.HexColor('#60738D')
    cell=ParagraphStyle('reportcell',fontName='Helvetica',fontSize=8,leading=11,textColor=ink)
    head=ParagraphStyle('reporthead',parent=cell,fontName='Helvetica-Bold',textColor=colors.white)
    no_data=ParagraphStyle('nodata',parent=cell,fontSize=10,leading=15)

    def label(s,style=cell):
        return Paragraph(escape(str(s)).replace('\n','<br/>'),style)

    data=[[label(c.replace('_',' ').title(),head) for c in cols]]
    data.extend([[label(v) for v in row] for row in rows])
    # A no-data report is still a valid document.
    if not rows:data.append([label('No records in this report',no_data)]+['']*(len(cols)-1))
    # Weight the main descriptive column; keep numeric columns legible.
    weights=[]
    for col in cols:
        key=col.casefold()
        weights.append(2.2 if key in ('name','customer','description','category') else (1.35 if key in ('created','month') else 1.0))
    scale=usable/sum(weights)
    widths=[weight*scale for weight in weights]
    table=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),primary),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F7FB')]),
        ('LINEBELOW',(0,0),(-1,0),1,accent),
        ('LINEBELOW',(0,1),(-1,-1),0.30,colors.HexColor('#E4EBF3')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),10),
        ('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,-1),9),
        ('BOTTOMPADDING',(0,0),(-1,-1),9),
    ]))

    def frame(canvas,document):
        canvas.saveState()
        # Top brand banner
        canvas.setFillColor(primary)
        canvas.rect(0,h-12,w,12,fill=1,stroke=0)
        logo_right=left
        if logo_path and logo_path.is_file():
            try:
                image=ImageReader(str(logo_path))
                iw,ih=image.getSize()
                factor=min(68/iw,55/ih)
                sw,sh=iw*factor,ih*factor
                canvas.drawImage(image,left,h-79,sw,sh,mask='auto',preserveAspectRatio=True)
                logo_right=left+sw+13
            except Exception:pass
        canvas.setFillColor(primary)
        canvas.setFont('Helvetica-Bold',15)
        canvas.drawString(logo_right,h-42,company[:77])
        canvas.setFont('Helvetica',8.5)
        canvas.setFillColor(muted)
        contact=[part for part in [address.replace('\n','  •  '),phone,email] if part]
        for i,line in enumerate(contact[:2]):
            canvas.drawString(logo_right,h-58-12*i,line[:125])
        canvas.setStrokeColor(accent);canvas.setLineWidth(1.5)
        canvas.line(left,h-90,w-right,h-90)
        canvas.setFillColor(primary);canvas.setFont('Helvetica-Bold',15)
        canvas.drawString(left,h-116,title[:78])
        canvas.setFont('Helvetica',9);canvas.setFillColor(muted)
        canvas.drawRightString(w-right,h-114,stamp.strftime('%B %d, %Y'))
        canvas.setStrokeColor(colors.HexColor('#E1E8F0'))
        canvas.line(left,40,w-right,40)
        canvas.setFont('Helvetica',8);canvas.setFillColor(muted)
        canvas.drawString(left,26,f'{company}  •  Generated {stamp:%Y-%m-%d %H:%M}')
        canvas.drawRightString(w-right,26,f'Page {document.page}')
        canvas.restoreState()

    doc.build([table],onFirstPage=frame,onLaterPages=frame)
    return Path(output)
