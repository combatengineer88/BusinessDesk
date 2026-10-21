"""Free-positioned, validated, per-document PDF layout definitions and renderer.

Coordinates are PDF points from the TOP LEFT of the page. Financial values always
come from original saved document rows, never template-supplied expressions.
"""
import copy
import json
import re
import uuid
from address_utils import customer_address
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

KINDS = ('Estimate', 'Invoice', 'PO')
PAGE_SIZES = {'Letter': letter, 'A4': A4}
TYPES = ('text', 'field', 'section', 'rectangle', 'line', 'logo', 'image', 'items', 'totals', 'notes', 'terms', 'footer')
FIELDS = ('business_name','business_address','business_phone','business_email','customer_name','customer_address',
          'customer_email','supplier_name','supplier_address','supplier_email','document_title','document_number',
          'date','due_date','subtotal','tax','total','notes','payment_terms','page_number')
DEFAULT_FONT = 'Helvetica'
MAX_OBJECTS = 110


def settings_key(kind):
    if kind not in KINDS:raise ValueError('Unknown document kind')
    return f'visual_template_{kind.lower()}'


def node(kind, x, y, w, h, text='', size=10, bold=False, color='#223047', **extra):
    record=dict(id=uuid.uuid4().hex[:12],type=kind,x=x,y=y,w=w,h=h,text=text,size=size,bold=bold,
                color=color,fill='#FFFFFF',align='left')
    record.update(extra)
    return record


def default_layout(kind):
    settings_key(kind)
    heading={'Estimate':'ESTIMATE','Invoice':'INVOICE','PO':'PURCHASE ORDER'}[kind]
    who='supplier' if kind=='PO' else 'customer'
    nodes=[
        node('rectangle',0,0,612,15,fill='#2563EB',color='#2563EB'),
        node('logo',42,41,90,65),
        node('field',146,40,380,31,'{{business_name}}',21,True,'#17263C'),
        node('field',146,76,405,52,'{{business_address}}\n{{business_phone}}  {{business_email}}',9,False,'#64748B'),
        node('line',42,138,528,1,color='#CBD5E1'),
        node('text',42,163,375,39,heading,27,True,'#17263C'),
        node('field',430,166,140,25,'#{{document_number}}',14,True,'#2563EB',align='right'),
        node('section',42,226,297,74,'BILL TO\n{{'+who+'_name}}\n{{'+who+'_address}}',10,False,'#223047'),
        node('section',376,226,194,69,'DOCUMENT DETAILS\nDate: {{date}}',10,False,'#223047'),
        node('items',42,329,528,218,'',10),
        node('notes',42,566,291,95,'NOTES',10),
        node('totals',367,566,203,92,'',11),
        node('footer',42,746,528,27,'Thank you for your business  •  Page {{page_number}}',8,color='#64748B',align='center'),
    ]
    return {'page_size':'Letter','accent':'#2563EB','objects':nodes}


def validate(kind, layout):
    settings_key(kind)
    if not isinstance(layout,dict):raise ValueError('Layout must be a JSON object')
    if set(layout) != {'page_size','accent','objects'}:raise ValueError('Unsupported layout properties')
    if layout['page_size'] not in PAGE_SIZES:raise ValueError('Invalid page size')
    if not isinstance(layout['accent'],str) or not re.fullmatch('#[0-9A-Fa-f]{6}',layout['accent']):
        raise ValueError('Accent must be a six-digit hex color')
    objs=layout['objects']
    if not isinstance(objs,list) or len(objs)>MAX_OBJECTS:raise ValueError('Too many elements in layout')
    page_w,page_h=PAGE_SIZES[layout['page_size']]
    ids=set(); table_count=0; total_count=0
    for obj in objs:
        if not isinstance(obj,dict):raise ValueError('Invalid element')
        required={'id','type','x','y','w','h','text','size','bold','color','fill','align'}
        if set(obj)!=required:raise ValueError('Unexpected element fields')
        if not isinstance(obj['id'],str) or not re.fullmatch('[a-zA-Z0-9_-]{1,40}',obj['id']) or obj['id'] in ids:
            raise ValueError('Duplicate or invalid element ID')
        ids.add(obj['id'])
        if obj['type'] not in TYPES:raise ValueError('Unknown element type')
        table_count+=obj['type']=='items';total_count+=obj['type']=='totals'
        if not all(isinstance(obj[k],(int,float)) and not isinstance(obj[k],bool) for k in ('x','y','w','h','size')):
            raise ValueError('Position, size, and font must be numbers')
        if not (0<=obj['x']<=page_w-5 and 0<=obj['y']<=page_h-5 and
                8<=obj['w']<=page_w and 1<=obj['h']<=page_h and
                obj['x']+obj['w']<=page_w+0.01 and obj['y']+obj['h']<=page_h+0.01):
            raise ValueError('Element outside page: '+obj['id'])
        if not 6<=obj['size']<=40:raise ValueError('Font size must be 6–40')
        if not isinstance(obj['bold'],bool):raise ValueError('Bold value must be true or false')
        if obj['align'] not in ('left','center','right'):raise ValueError('Invalid alignment')
        for k in ('color','fill'):
            if not isinstance(obj[k],str) or not re.fullmatch('#[0-9A-Fa-f]{6}',obj[k]):raise ValueError('Invalid element color')
        if not isinstance(obj['text'],str) or len(obj['text'])>2500 or '\x00' in obj['text']:
            raise ValueError('Text exceeds limit or contains illegal characters')
        if obj['type']=='image' and obj['text'] and not Path(obj['text']).is_absolute():
            raise ValueError('Image must use an absolute local path')
    if table_count>1 or total_count>1:raise ValueError('Only one repeating items table and totals block are supported')
    return copy.deepcopy(layout)


def load(db,kind):
    row=db.execute('SELECT value FROM settings WHERE key=?',(settings_key(kind),)).fetchone()
    if not row:return None
    return validate(kind,json.loads(row[0]))


def save(db,kind,layout):
    safe=validate(kind,layout)
    with db:
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',
                   (settings_key(kind),json.dumps(safe,ensure_ascii=False)))


def reset(db,kind):
    with db:db.execute('DELETE FROM settings WHERE key=?',(settings_key(kind),))


def sample_data(kind):
    company={'business_name':'TDZIGNS LLC','business_address':'1800 Market Street\nWatertown, WI',
             'business_phone':'(555) 555-0198','business_email':'sales@example.com'}
    return dict(company,customer_name='Example Customer',customer_address='123 Sample Road\nMadison, WI 53703',
                customer_email='customer@example.com',supplier_name='Example Supplier',supplier_address='44 Supply Park\nMilwaukee, WI',
                supplier_email='supplier@example.com',document_title={'Estimate':'Estimate','Invoice':'Invoice','PO':'Purchase Order'}[kind],
                document_number='PREVIEW',date='2026-10-19',subtotal='$385.00',tax='$21.18' if kind!='PO' else '$0.00',
                total='$406.18' if kind!='PO' else '$385.00',notes='Thank you for considering our services.\nContact us with questions.',
                payment_terms='Net 30',page_number='1',_rows=[('Custom T-Shirt',4,2500,10000),('Custom Vinyl Decals',15,1900,28500)],
                _subtotal=38500,_tax=2118 if kind!='PO' else 0,_total=40618 if kind!='PO' else 38500,
                _logo='')


def document_data(db,kind,record_id,preview=False):
    if preview:
        result=sample_data(kind)
    else:
        if kind=='PO':
            row=db.execute('SELECT p.*,s.name,s.address,s.email FROM purchase_orders p JOIN suppliers s ON p.supplier_id=s.id WHERE p.id=?',(record_id,)).fetchone()
            if row is None:raise ValueError('Purchase order not found')
            items=db.execute('SELECT p.name, i.qty, i.unit_cost FROM po_items i JOIN products p ON p.id=i.product_id WHERE i.po_id=? ORDER BY i.id',(record_id,)).fetchall()
            total=int(row['total']); tax=0
        else:
            postal='c.city,c.state,c.zip_code' if {'city','state','zip_code'} <= {r[1] for r in db.execute('PRAGMA table_info(customers)')} else "'' AS city,'' AS state,'' AS zip_code"
            row=db.execute(f'SELECT d.*,c.name,c.address,c.email,{postal} FROM documents d JOIN customers c ON d.customer_id=c.id WHERE d.id=?',(record_id,)).fetchone()
            if row is None or row['kind']!=kind:raise ValueError('Document not found or wrong type')
            items=db.execute('SELECT description,qty,unit_price FROM document_items WHERE document_id=? ORDER BY id',(record_id,)).fetchall()
            total=int(row['total']); tax=int(row['tax'])
        money=lambda amount:f'${amount/100:,.2f}'
        subtotal=int(row['total']) if kind=='PO' else int(row['subtotal'])
        result={
            'customer_name':row['name'] if kind!='PO' else '',
            'supplier_name':row['name'] if kind=='PO' else '',
            'customer_address':customer_address(row['address'],row['city'],row['state'],row['zip_code']) if kind!='PO' else '',
            'supplier_address':(row['address'] or '') if kind=='PO' else '',
            'customer_email':(row['email'] or '') if kind!='PO' else '',
            'supplier_email':(row['email'] or '') if kind=='PO' else '',
            'document_title':{'Estimate':'Estimate','Invoice':'Invoice','PO':'Purchase Order'}[kind],
            'document_number':str(record_id),
            'date': row['ordered_on'] if kind=='PO' else row['created'],
            'due_date': row['credit_due_on'] if kind!='PO' and 'credit_due_on' in row.keys() else '',
            'subtotal':money(subtotal),'tax':money(tax),'total':money(total),
            'notes':row['notes'] or '',
            'payment_terms':'', 'page_number':'1',
            '_rows':[(i[0],int(i[1]),int(i[2]),int(i[1])*int(i[2])) for i in items],
            '_subtotal':subtotal,'_tax':tax,'_total':total,
        }
        if result['due_date']:
            result['payment_terms']='Due '+result['due_date']
    settings={r['key']:r['value'] for r in db.execute('SELECT key,value FROM settings')}
    if not preview:
        result.update({
            'business_name':settings.get('business_name','TDZIGNS LLC'),
            'business_address':settings.get('business_address',''),
            'business_phone':settings.get('business_phone',''),
            'business_email':settings.get('business_email',''),
        })
    result['_logo']=settings.get('logo_path','') if not preview else ''
    return result


TAG=re.compile(r'\{\{([a-z_]+)\}\}')

def resolve(text,data):
    return TAG.sub(lambda m: str(data.get(m.group(1),'') if m.group(1) in FIELDS else ''),text)


def _color(hexvalue):return colors.HexColor(hexvalue)


def _draw_text(pdf,text,x,top,w,h,fontsize,color,bold=False,align='left',page_h=792):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    pdf.setFillColor(_color(color))
    font='Helvetica-Bold' if bold else DEFAULT_FONT
    pdf.setFont(font,fontsize)
    leading=fontsize*1.32
    max_lines=max(1,int(h//leading))
    lines=[]
    for part in text.replace('\r','').split('\n'):
        current=''
        for word in part.split(' '):
            guess=(current+' '+word).strip()
            if current and stringWidth(guess,font,fontsize)>w:
                lines.append(current);current=word
            else:current=guess
        lines.append(current)
    for i,line in enumerate(lines[:max_lines]):
        line=line[:240]
        y=page_h-(top+fontsize+i*leading)
        if align=='center':pdf.drawCentredString(x+w/2,y,line)
        elif align=='right':pdf.drawRightString(x+w,y,line)
        else:pdf.drawString(x,y,line)


def _draw_node(pdf,obj,data,page_height,dy=0,preview=False):
    typ=obj['type'];x=float(obj['x']); y=float(obj['y'])+dy; w=float(obj['w']); h=float(obj['h'])
    pdf.saveState()
    pdf.setStrokeColor(_color(obj['color']))
    pdf.setFillColor(_color(obj['fill']))
    if typ=='rectangle':
        pdf.rect(x,page_height-y-h,w,h,fill=1,stroke=0)
    elif typ=='line':
        pdf.setLineWidth(1.2);pdf.line(x,page_height-y,x+w,page_height-y)
    elif typ in ('logo','image'):
        path=data.get('_logo','') if typ=='logo' else obj['text']
        if path and Path(path).is_file():
            try:
                rw,rh=ImageReader(path).getSize();sc=min(w/rw,h/rh)
                pw,ph=rw*sc,rh*sc
                pdf.drawImage(path,x+(w-pw)/2,page_height-y-(h+ph)/2,width=pw,height=ph,mask='auto')
            except (OSError,ValueError):pass
        elif preview:
            pdf.setStrokeColor(colors.HexColor('#D4DBE5'));pdf.rect(x,page_height-y-h,w,h,fill=0,stroke=1)
            _draw_text(pdf,'LOGO' if typ=='logo' else 'IMAGE',x,y+10,w,h-10,10,'#94A3B8',align='center',page_h=page_height)
    elif typ=='section':
        pieces=resolve(obj['text'],data).split('\n',1)
        _draw_text(pdf,pieces[0],x,y,w,22,float(obj['size']),obj['color'],True,obj['align'],page_height)
        if len(pieces)>1:
            _draw_text(pdf,pieces[1],x,y+23,w,max(8,h-23),min(float(obj['size']),10),obj['color'],False,obj['align'],page_height)
    elif typ in ('text','field','notes','terms','footer'):
        content=resolve(obj['text'],data)
        if typ=='notes':content=(content or 'NOTES')+'\n'+data.get('notes','')
        if typ=='terms':content=(content or 'TERMS')+'\n'+data.get('payment_terms','')
        _draw_text(pdf,content,x,y,w,h,float(obj['size']),obj['color'],obj['bold'],obj['align'],page_height)
    pdf.restoreState()


def _draw_items(pdf,obj,data,page_h,y,rows,header=True):
    x=obj['x'];w=obj['w'];fontsize=max(8,min(12,int(obj['size'])));rh=28;head_h=32
    pdf.saveState()
    if header:
        pdf.setFillColor(_color(data.get('_accent','#1E3A5F')));pdf.roundRect(x,page_h-y-head_h,w,head_h,4,fill=1,stroke=0)
        labels=('Description','Qty','Unit price' if data['document_title']!='Purchase Order' else 'Unit cost','Amount')
        spans=[x+10,x+w*.54,x+w*.67,x+w-8]
        pdf.setFillColor(colors.white);pdf.setFont('Helvetica-Bold',9)
        for i,label in enumerate(labels):
            xx=spans[i]
            pdf.drawRightString(xx,page_h-y-21,label) if i==3 else pdf.drawString(xx,page_h-y-21,label)
    money=lambda val:f'${val/100:,.2f}'
    for i,row in enumerate(rows):
        yy=y+head_h+i*rh
        pdf.setFillColor(colors.HexColor('#F1F5F9') if i%2 else colors.white)
        pdf.rect(x,page_h-yy-rh,w,rh,fill=1,stroke=0)
        pdf.setFillColor(colors.HexColor('#223047'));pdf.setFont('Helvetica',fontsize)
        text=str(row[0])
        from reportlab.pdfbase.pdfmetrics import stringWidth
        while text and stringWidth(text,'Helvetica',fontsize)>w*.48:text=text[:-1]
        pdf.drawString(x+10,page_h-yy-18,text)
        pdf.drawRightString(x+w*.62,page_h-yy-18,str(row[1]))
        pdf.drawRightString(x+w*.82,page_h-yy-18,money(row[2]))
        pdf.drawRightString(x+w-8,page_h-yy-18,money(row[3]))
    pdf.setStrokeColor(colors.HexColor('#E2E8F0'))
    pdf.line(x,page_h-(y+head_h+len(rows)*rh),x+w,page_h-(y+head_h+len(rows)*rh))
    pdf.restoreState()
    return head_h+len(rows)*rh


def _draw_totals(pdf,obj,data,page_h,top):
    x,w=obj['x'],obj['w']
    pdf.saveState()
    rows=[('Subtotal',data['subtotal'])]
    if data['document_title']!='Purchase Order':rows.append(('Tax',data['tax']))
    rows.append(('TOTAL',data['total']))
    for i,(label,value) in enumerate(rows):
        yy=page_h-(top+i*24+15)
        font='Helvetica-Bold' if label=='TOTAL' else 'Helvetica'
        pdf.setFont(font,11 if label=='TOTAL' else 9)
        pdf.setFillColor(_color(obj['color']) if label=='TOTAL' else colors.HexColor('#46566B'))
        pdf.drawString(x,yy,label)
        pdf.drawRightString(x+w,yy,value)
    pdf.restoreState()


def render(db,kind,record_id,output,layout=None,preview=False):
    """Render a free-positioned PDF; long item tables automatically continue on pages."""
    layout=validate(kind,layout) if layout is not None else load(db,kind)
    if layout is None:layout=default_layout(kind)
    data=document_data(db,kind,record_id,preview)
    data['_accent']=layout['accent']
    page_w,page_h=PAGE_SIZES[layout['page_size']]
    items=next((obj for obj in layout['objects'] if obj['type']=='items'),None)
    other=[obj for obj in layout['objects'] if obj['type']!='items']
    rows=data['_rows']
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    pdf=pdfcanvas.Canvas(str(out),pagesize=(page_w,page_h))
    pdf.setTitle(f"{kind} #{data['document_number']}")
    if not items:
        page_count=1
    else:
        first_capacity=max(1,int(max(38,items['h']-32)//28))
        next_capacity=max(1,int((page_h-370)//28))
        remaining=max(0,len(rows)-first_capacity)
        page_count=1+(remaining+next_capacity-1)//next_capacity
    first_capacity=max(1,int(max(38,items['h']-32)//28)) if items else 0
    next_capacity=max(1,int((page_h-370)//28)) if items else 0
    consumed=0
    for page in range(1,page_count+1):
        data['page_number']=str(page)
        if page==1:
            for obj in other:
                if obj['type'] in ('totals','notes','terms','footer'):continue
                _draw_node(pdf,obj,data,page_h,preview=preview)
        else:
            pdf.setFont('Helvetica-Bold',10);pdf.setFillColor(colors.HexColor('#223047'))
            pdf.drawString(42,page_h-45,data['document_title'].upper()+' #'+data['document_number']+' (continued)')
        current_top=items['y'] if page==1 and items else 85
        shown=0
        if items:
            cap=first_capacity if page==1 else next_capacity
            batch=rows[consumed:consumed+cap];consumed+=len(batch)
            shown=_draw_items(pdf,items,data,page_h,current_top,batch)
        if page==page_count:
            for obj in other:
                if obj['type'] not in ('totals','notes','terms'):continue
                if items:
                    table_end=current_top+shown
                    original_table_end=items['y']+items['h']
                    if page==1:
                        top=max(obj['y'],table_end+12) if obj['y']>=items['y'] else obj['y']
                    else:
                        top=table_end+20+max(0,obj['y']-original_table_end)
                    top=min(top,page_h-obj['h']-48)
                else:top=obj['y']
                if obj['type']=='totals':_draw_totals(pdf,obj,data,page_h,top)
                else:_draw_node(pdf,obj,data,page_h,dy=top-obj['y'],preview=preview)
        for obj in other:
            if obj['type']=='footer':_draw_node(pdf,obj,data,page_h,preview=preview)
        if preview:
            pdf.saveState();pdf.setFillColor(colors.HexColor('#CBD5E1'))
            pdf.translate(page_w/2,page_h/2);pdf.rotate(38);pdf.setFont('Helvetica-Bold',32)
            pdf.drawCentredString(0,0,'SAMPLE PREVIEW');pdf.restoreState()
        pdf.showPage()
    pdf.save()
    return out
