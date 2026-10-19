"""WYSIWYG-like Tkinter canvas editor for BusinessDesk document layouts.

A single Letter/A4 page serves as the master layout. The repeating items block
flows to continuation pages in the PDF renderer. Coordinates use PDF points.
"""
import copy
import os
import shutil
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from visual_templates import (KINDS, TYPES, FIELDS, PAGE_SIZES, default_layout,
                              load, save, reset, validate, node, render, sample_data,resolve)

BACKGROUND='#F1F5F9'; INK='#17263C'; BLUE='#2563EB'; GRAY='#64748B'
TOOL_CHOICES=[('Text box','text'),('Dynamic field','field'),('Custom section','section'),
              ('Rectangle / color block','rectangle'),('Divider line','line'),
              ('Company logo','logo'),('Custom image','image'),
              ('Repeating items table','items'),('Totals','totals'),('Document notes','notes'),
              ('Payment / supplier terms','terms'),('Page footer','footer')]


class VisualTemplateEditor:
    def __init__(self,parent,db,storage):
        self.db=db;self.storage=Path(storage)
        self.kind='Estimate';self.layout=load(db,self.kind) or default_layout(self.kind)
        self.selected=None;self.drag=None;self.scale=.85;self.snap=tk.BooleanVar(value=True)
        self.undo_stack=[];self.redo_stack=[];self.dirty=False
        self.window=tk.Toplevel(parent);self.window.title('BusinessDesk  •  Visual Document Designer')
        sw,sh=self.window.winfo_screenwidth(),self.window.winfo_screenheight()
        self.window.geometry(f'{min(1430,max(1030,sw-70))}x{min(900,max(680,sh-85))}')
        self.window.minsize(1030,680)
        self.window.transient(parent)
        self.window.configure(background=BACKGROUND)
        self._build()
        self._render()
        self.window.bind('<Delete>',lambda e:self.remove_selected() if not self._text_focused() else None)
        self.window.bind('<Control-d>',lambda e:self.duplicate() if not self._text_focused() else None)
        self.window.bind('<Control-z>',lambda e:self.undo() if not self._text_focused() else None)
        self.window.bind('<Control-y>',lambda e:self.redo() if not self._text_focused() else None)
        self.window.bind('<Control-s>',lambda e:self.save() if not self._text_focused() else None)
        for key,delta in [('Left',(-2,0)),('Right',(2,0)),('Up',(0,-2)),('Down',(0,2))]:
            self.window.bind('<'+key+'>',lambda e,d=delta:self.nudge(*d) if not self._text_focused() else None)
        self.window.protocol('WM_DELETE_WINDOW',self.close)

    def _build(self):
        top=ttk.Frame(self.window,style='Surface.TFrame',padding=(20,14));top.pack(fill='x')
        ttk.Label(top,text='Visual Template Designer',style='PageTitle.TLabel').pack(side='left')
        ttk.Label(top,text='Drag  •  Resize  •  Customize  •  Preview',style='Subtle.TLabel').pack(side='left',padx=18)
        ttk.Button(top,text='Save design',style='Accent.TButton',command=self.save).pack(side='right',padx=4)
        ttk.Button(top,text='Preview PDF',command=self.preview).pack(side='right',padx=4)
        ttk.Button(top,text='Restore design',command=self.restore).pack(side='right',padx=4)
        selector=ttk.Frame(self.window,padding=(18,8));selector.pack(fill='x')
        ttk.Label(selector,text='Document type',font=('Segoe UI',10,'bold')).pack(side='left')
        self.kind_var=tk.StringVar(value='Estimate')
        chooser=ttk.Combobox(selector,textvariable=self.kind_var,values=KINDS,state='readonly',width=17)
        chooser.pack(side='left',padx=(10,20));chooser.bind('<<ComboboxSelected>>',self.change_kind)
        ttk.Label(selector,text='Paper',style='Subtle.TLabel').pack(side='left')
        self.page_var=tk.StringVar(value=self.layout['page_size'])
        paper=ttk.Combobox(selector,textvariable=self.page_var,values=list(PAGE_SIZES),state='readonly',width=10)
        paper.pack(side='left',padx=(7,15));paper.bind('<<ComboboxSelected>>',self.change_paper)
        ttk.Label(selector,text='Accent',style='Subtle.TLabel').pack(side='left')
        ttk.Button(selector,text='Choose color',command=self.choose_accent).pack(side='left',padx=7)
        ttk.Checkbutton(selector,text='Snap to 6 pt grid',variable=self.snap,command=self._render).pack(side='left',padx=18)
        ttk.Label(selector,text='Zoom',style='Subtle.TLabel').pack(side='left')
        ttk.Button(selector,text='−',width=3,command=lambda:self.zoom(-.1)).pack(side='left',padx=4)
        self.zoom_label=ttk.Label(selector,text='85%');self.zoom_label.pack(side='left')
        ttk.Button(selector,text='+',width=3,command=lambda:self.zoom(.1)).pack(side='left',padx=4)
        middle=ttk.Frame(self.window,padding=(14,6,14,4));middle.pack(fill='both',expand=True)
        middle.columnconfigure(0,minsize=218);middle.columnconfigure(1,weight=1);middle.columnconfigure(2,minsize=287)
        middle.rowconfigure(0,weight=1)
        left=ttk.Frame(middle,style='Surface.TFrame',padding=12);left.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        ttk.Label(left,text='ADD OBJECTS',style='SideHeading.TLabel').pack(anchor='w',pady=(0,8))
        self.toolbox=ttk.Frame(left,style='Surface.TFrame');self.toolbox.pack(fill='x')
        for label,typ in TOOL_CHOICES:
            ttk.Button(self.toolbox,text='＋  '+label,command=lambda t=typ:self.add(t),style='Tool.TButton').pack(fill='x',pady=2)
        ttk.Separator(left).pack(fill='x',pady=12)
        ttk.Label(left,text='INSERT DATA FIELD',style='SideHeading.TLabel').pack(anchor='w',pady=(0,5))
        self.field_var=tk.StringVar(value='customer_name')
        ttk.Combobox(left,textvariable=self.field_var,values=FIELDS,state='readonly').pack(fill='x',pady=4)
        ttk.Button(left,text='Add selected field',command=self.add_field).pack(fill='x',pady=3)
        ttk.Separator(left).pack(fill='x',pady=12)
        ttk.Label(left,text='OBJECT LAYERS',style='SideHeading.TLabel').pack(anchor='w',pady=(0,5))
        self.layers=tk.Listbox(left,height=11,background='#F8FAFC',foreground=INK,borderwidth=0,
                               selectbackground='#DBEAFE',selectforeground='#1E40AF',activestyle='none',font=('Segoe UI',9))
        self.layers.pack(fill='both',expand=True)
        self.layers.bind('<<ListboxSelect>>',self._from_layers)
        layer_buttons=ttk.Frame(left,style='Surface.TFrame');layer_buttons.pack(fill='x',pady=8)
        ttk.Button(layer_buttons,text='Bring front',command=lambda:self.layer(1)).pack(side='left',padx=3)
        ttk.Button(layer_buttons,text='Send back',command=lambda:self.layer(-1)).pack(side='left',padx=3)
        center=ttk.Frame(middle);center.grid(row=0,column=1,sticky='nsew',padx=(0,8))
        ttk.Label(center,text='PAGE CANVAS   •   Drag objects to move, drag the blue corner to resize',style='Subtle.TLabel').pack(anchor='w',padx=7,pady=6)
        stage=ttk.Frame(center);stage.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(stage,bg='#E8EDF5',highlightthickness=0,bd=0,cursor='arrow')
        scroll_y=ttk.Scrollbar(stage,orient='vertical',command=self.canvas.yview)
        scroll_x=ttk.Scrollbar(stage,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=scroll_y.set,xscrollcommand=scroll_x.set)
        scroll_y.pack(side='right',fill='y');scroll_x.pack(side='bottom',fill='x')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.bind('<Button-1>',self._press)
        self.canvas.bind('<B1-Motion>',self._move)
        self.canvas.bind('<ButtonRelease-1>',self._release)
        right=ttk.Frame(middle,style='Surface.TFrame',padding=14);right.grid(row=0,column=2,sticky='nsew')
        ttk.Label(right,text='OBJECT PROPERTIES',style='SideHeading.TLabel').pack(anchor='w',pady=(0,7))
        self.selected_label=ttk.Label(right,text='Select an object on the page.',style='Subtle.TLabel')
        self.selected_label.pack(fill='x',pady=(0,8))
        props=ttk.Frame(right,style='Surface.TFrame');props.pack(fill='x')
        self.props={}
        for i,(key,label) in enumerate([('x','X (pt)'),('y','Y (pt)'),('w','Width'),('h','Height'),('size','Font size')]):
            ttk.Label(props,text=label,style='Property.TLabel').grid(row=i,column=0,sticky='w',pady=4)
            v=tk.StringVar();self.props[key]=v
            ttk.Entry(props,textvariable=v,width=15).grid(row=i,column=1,sticky='ew',padx=(8,0),pady=4)
        props.columnconfigure(1,weight=1)
        ttk.Label(right,text='Text / placeholder / section heading',style='Property.TLabel').pack(anchor='w',pady=(12,5))
        self.property_text=tk.Text(right,height=6,width=30,wrap='word',font=('Segoe UI',10),bg='#FAFCFF',fg=INK,
                                   relief='solid',borderwidth=1,insertbackground=INK)
        self.property_text.pack(fill='x')
        alignbox=ttk.Frame(right,style='Surface.TFrame');alignbox.pack(fill='x',pady=8)
        self.align=tk.StringVar(value='left')
        ttk.Label(alignbox,text='Align',style='Property.TLabel').pack(side='left')
        ttk.Combobox(alignbox,textvariable=self.align,values=['left','center','right'],state='readonly',width=11).pack(side='right')
        self.bold=tk.BooleanVar(value=False)
        ttk.Checkbutton(right,text='Bold text',variable=self.bold).pack(anchor='w',pady=3)
        ttk.Button(right,text='Text / border color',command=lambda:self.pick_color('color')).pack(fill='x',pady=4)
        ttk.Button(right,text='Background / fill color',command=lambda:self.pick_color('fill')).pack(fill='x',pady=4)
        ttk.Button(right,text='Apply changes',style='Accent.TButton',command=self.apply_props).pack(fill='x',pady=(12,5))
        ttk.Button(right,text='Duplicate object',command=self.duplicate).pack(fill='x',pady=3)
        ttk.Button(right,text='Delete object',command=self.remove_selected).pack(fill='x',pady=3)
        ttk.Separator(right).pack(fill='x',pady=14)
        ttk.Label(right,text='TIPS',style='SideHeading.TLabel').pack(anchor='w',pady=5)
        ttk.Label(right,text=('• Click then drag an element.\n• Use the blue corner to resize.\n'
                             '• Arrow keys nudge positions.\n• Ctrl+D duplicates; Delete removes.\n'
                             '• Use {{customer_name}}, {{total}},\n  and other placeholders for live data.\n'
                             '• The product table continues on\n  additional PDF pages when needed.'),
                  style='Subtle.TLabel',justify='left',wraplength=252).pack(anchor='w')
        self.message=tk.StringVar(value='Select an object or add a new one. Changes are not saved until you click Save design.')
        status=ttk.Frame(self.window,style='Surface.TFrame',padding=(20,9));status.pack(fill='x')
        ttk.Label(status,textvariable=self.message,style='Subtle.TLabel').pack(side='left')
        ttk.Button(status,text='Close designer',command=self.close).pack(side='right')

    def _text_focused(self):
        widget=self.window.focus_get()
        return isinstance(widget,(tk.Entry,ttk.Entry,tk.Text,ttk.Combobox))

    def _get(self):
        if not self.selected:return None
        return next((o for o in self.layout['objects'] if o['id']==self.selected),None)

    def _record(self):
        self.undo_stack.append(copy.deepcopy(self.layout))
        if len(self.undo_stack)>50:self.undo_stack.pop(0)
        self.redo_stack.clear();self.dirty=True

    def _set_object(self,updated):
        old=self._get()
        if old is None:return
        for i,o in enumerate(self.layout['objects']):
            if o['id']==old['id']:self.layout['objects'][i]=updated;break
        self._render();self._properties()

    def _render(self):
        c=self.canvas;c.delete('all')
        pw,ph=PAGE_SIZES[self.layout['page_size']];s=self.scale
        ox,oy=32,30
        c.configure(scrollregion=(0,0,pw*s+95,ph*s+75))
        c.create_rectangle(ox+6,oy+7,ox+pw*s+6,oy+ph*s+7,fill='#D2DAE5',outline='')
        c.create_rectangle(ox,oy,ox+pw*s,oy+ph*s,fill='#FFFFFF',outline='#D7DFE8',width=1)
        if self.snap.get():
            for xx in range(0,int(pw),24):c.create_line(ox+xx*s,oy,ox+xx*s,oy+ph*s,fill='#F1F5FA')
            for yy in range(0,int(ph),24):c.create_line(ox,oy+yy*s,ox+pw*s,oy+yy*s,fill='#F1F5FA')
        data=sample_data(self.kind)
        data['business_name']='TDZIGNS LLC'
        for o in self.layout['objects']:
            x1,y1=ox+o['x']*s,oy+o['y']*s
            x2,y2=x1+o['w']*s,y1+o['h']*s
            tags=('node',o['id'])
            typ=o['type']
            if typ=='rectangle':
                c.create_rectangle(x1,y1,x2,y2,fill=o['fill'],outline='',tags=tags)
            elif typ=='line':
                c.create_line(x1,y1,x2,y1,fill=o['color'],width=2,tags=tags)
            elif typ in ('logo','image'):
                c.create_rectangle(x1,y1,x2,y2,fill='#F1F5F9',outline='#B7C5D8',dash=(3,3),tags=tags)
                c.create_text((x1+x2)/2,(y1+y2)/2,text='COMPANY LOGO' if typ=='logo' else 'IMAGE',
                              fill=GRAY,font=('Segoe UI',9,'bold'),tags=tags)
            elif typ=='items':
                c.create_rectangle(x1,y1,x2,y2,outline='#B7C5D8',width=1,tags=tags)
                c.create_rectangle(x1,y1,x2,y1+30*s,fill='#1E3A5F',outline='',tags=tags)
                c.create_text(x1+10,y1+15*s,anchor='w',text='DESCRIPTION             QTY          UNIT PRICE       AMOUNT',
                              fill='#FFFFFF',font=('Segoe UI',max(7,int(9*s)),'bold'),tags=tags)
                for j,line in enumerate(data['_rows']):
                    yy=y1+30*s+(j+1)*26*s
                    if yy>y2:break
                    c.create_line(x1,yy,x2,yy,fill='#DFE6EF',tags=tags)
                    c.create_text(x1+10,yy-11*s,anchor='w',text=line[0],font=('Segoe UI',max(7,int(9*s))),fill=INK,tags=tags)
            elif typ=='totals':
                c.create_rectangle(x1,y1,x2,y2,fill='#F7F9FC',outline='#E2E8F0',tags=tags)
                for j,(label,value) in enumerate([('Subtotal','$385.00'),('Tax','$21.18'),('TOTAL','$406.18')]):
                    c.create_text(x1+9,y1+(16+j*23)*s,anchor='w',text=label,fill=INK,font=('Segoe UI',9,'bold' if j==2 else 'normal'),tags=tags)
                    c.create_text(x2-9,y1+(16+j*23)*s,anchor='e',text=value,fill=INK,font=('Segoe UI',9,'bold' if j==2 else 'normal'),tags=tags)
            else:
                text=resolve(o['text'],data)
                if typ=='notes':text=(text or 'NOTES')+'\nSample document notes'
                if typ=='terms':text=(text or 'TERMS')+'\nNet 30'
                c.create_text(x1+3 if o['align']=='left' else (x2-3 if o['align']=='right' else (x1+x2)/2),y1+3,
                              anchor='nw' if o['align']=='left' else ('ne' if o['align']=='right' else 'n'),
                              width=max(5,(x2-x1)-6),text=text,fill=o['color'],
                              font=('Segoe UI',max(7,int(o['size']*s)),'bold' if o['bold'] or typ=='section' else 'normal'),tags=tags)
            if o['id']==self.selected:
                c.create_rectangle(x1,y1,x2,y2,outline=BLUE,width=2,dash=(5,2),tags=('selection',o['id']))
                c.create_rectangle(x2-6,y2-6,x2+5,y2+5,fill=BLUE,outline='#FFFFFF',tags=('resize',o['id']))
        self.layers.delete(0,'end')
        for o in reversed(self.layout['objects']):
            summary=(o['text'].split('\n',1)[0][:24] or o['type'].title())
            self.layers.insert('end',f"{o['type'].upper():10} {summary}")
        if self.selected:
            reverse_ids=[o['id'] for o in reversed(self.layout['objects'])]
            if self.selected in reverse_ids:
                index=reverse_ids.index(self.selected);self.layers.selection_clear(0,'end')
                self.layers.selection_set(index);self.layers.see(index)
        self.zoom_label.config(text=f'{int(s*100)}%')

    def _from_layers(self,_event):
        choice=self.layers.curselection()
        if not choice:return
        objects=list(reversed(self.layout['objects']))
        if choice[0]>=len(objects):return
        new=objects[choice[0]]['id']
        if new!=self.selected:self.selected=new;self._render();self._properties()

    def _at(self,event):
        cx,cy=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        return (cx-32)/self.scale,(cy-30)/self.scale

    def _press(self,event):
        x,y=self._at(event)
        found=None;action='move'
        for o in reversed(self.layout['objects']):
            if o['x']-1<=x<=o['x']+o['w']+3 and o['y']-1<=y<=o['y']+o['h']+3:
                found=o
                if abs(x-o['x']-o['w'])<14 and abs(y-o['y']-o['h'])<14:action='resize'
                break
        self.selected=found['id'] if found else None
        self.drag={'id':self.selected,'x':x,'y':y,'obj':copy.deepcopy(found),'action':action,'changed':False} if found else None
        self._render();self._properties()

    def _move(self,event):
        if not self.drag:return
        obj=self._get()
        if obj is None:return
        x,y=self._at(event);delta_x=x-self.drag['x'];delta_y=y-self.drag['y']
        old=self.drag['obj'];pw,ph=PAGE_SIZES[self.layout['page_size']]
        snap=lambda v:round(v/6)*6 if self.snap.get() else round(v)
        updated=copy.deepcopy(obj)
        if self.drag['action']=='move':
            updated['x']=max(0,min(pw-old['w'],snap(old['x']+delta_x)))
            updated['y']=max(0,min(ph-old['h'],snap(old['y']+delta_y)))
        else:
            updated['w']=max(12,min(pw-old['x'],snap(old['w']+delta_x)))
            updated['h']=max(12,min(ph-old['y'],snap(old['h']+delta_y)))
        if any(updated[k]!=old[k] for k in ('x','y','w','h')):
            if not self.drag['changed']:
                self._record();self.drag['changed']=True
            self._set_object(updated)

    def _release(self,event):
        self.drag=None

    def _properties(self):
        o=self._get()
        self.selected_label.config(text=(o['type'].upper()+'  •  '+o['id']) if o else 'No object selected')
        for key,var in self.props.items():var.set(str(o[key]) if o else '')
        self.property_text.delete('1.0','end')
        if o:self.property_text.insert('1.0',o['text'])
        self.bold.set(bool(o['bold']) if o else False)
        self.align.set(o['align'] if o else 'left')

    def add(self,typ):
        if len(self.layout['objects'])>=110:
            messagebox.showwarning('Object limit','Maximum of 110 objects.',parent=self.window);return
        if typ in ('items','totals') and any(o['type']==typ for o in self.layout['objects']):
            messagebox.showinfo('Existing object',f'There is already a {typ} block. Move or resize it instead.',parent=self.window);return
        label={'text':'Double-click to edit','field':'{{customer_name}}','section':'NEW SECTION\nSection content or {{customer_name}}',
               'notes':'NOTES','terms':'TERMS & CONDITIONS','footer':'Page {{page_number}}','image':''}.get(typ,'')
        positions={'line':(110,185,200,4),'rectangle':(110,185,240,40),'items':(42,320,528,200),
                   'totals':(355,560,210,90),'logo':(60,175,100,60),'image':(60,175,100,65)}
        x,y,w,h=positions.get(typ,(80,175,260,72))
        if typ=='footer':x,y,w,h=50,746,512,30
        if typ=='image':
            file=filedialog.askopenfilename(title='Select document image',filetypes=[('Images','*.png *.jpg *.jpeg')],parent=self.window)
            if not file:return
            folder=self.storage/'template_images';folder.mkdir(parents=True,exist_ok=True)
            dest=folder/(uuid.uuid4().hex+Path(file).suffix.lower());shutil.copy2(file,dest);label=str(dest)
        self._record()
        obj=node(typ,x,y,w,h,label)
        self.layout['objects'].append(obj)
        self.selected=obj['id'];self._render();self._properties()
        self.message.set('New '+typ+' created. Drag it to position or edit its properties.')

    def add_field(self):
        self.add('field')
        if self.selected:
            o=self._get();o['text']='{{'+self.field_var.get()+'}}'
            self._render();self._properties()

    def apply_props(self):
        old=self._get()
        if not old:return
        try:
            obj=copy.deepcopy(old)
            for k in ('x','y','w','h','size'):
                obj[k]=float(self.props[k].get())
            obj['text']=self.property_text.get('1.0','end-1c')
            obj['bold']=self.bold.get();obj['align']=self.align.get()
            test=copy.deepcopy(self.layout)
            for i,item in enumerate(test['objects']):
                if item['id']==obj['id']:test['objects'][i]=obj;break
            validate(self.kind,test)
            self._record();self._set_object(obj)
            self.message.set('Properties applied. Save design to keep them.')
        except Exception as exc:messagebox.showerror('Invalid properties',str(exc),parent=self.window)

    def remove_selected(self):
        if not self.selected:return
        self._record();self.layout['objects']=[o for o in self.layout['objects'] if o['id']!=self.selected]
        self.selected=None;self._render();self._properties()

    def duplicate(self):
        obj=self._get()
        if obj is None or obj['type'] in ('items','totals'):return
        self._record();new=copy.deepcopy(obj);new['id']=uuid.uuid4().hex[:12]
        pw,ph=PAGE_SIZES[self.layout['page_size']]
        new['x']=min(pw-new['w'],new['x']+18);new['y']=min(ph-new['h'],new['y']+18)
        self.layout['objects'].append(new);self.selected=new['id'];self._render();self._properties()

    def layer(self,direction):
        obj=self._get()
        if obj is None:return
        self._record();self.layout['objects'].remove(obj)
        if direction>0:self.layout['objects'].append(obj)
        else:self.layout['objects'].insert(0,obj)
        self._render()

    def nudge(self,dx,dy):
        obj=self._get()
        if obj is None:return
        self._record();pw,ph=PAGE_SIZES[self.layout['page_size']]
        obj['x']=max(0,min(pw-obj['w'],obj['x']+dx))
        obj['y']=max(0,min(ph-obj['h'],obj['y']+dy))
        self._render();self._properties()

    def undo(self):
        if not self.undo_stack:return
        self.redo_stack.append(copy.deepcopy(self.layout));self.layout=self.undo_stack.pop()
        self.selected=None;self.dirty=True;self._render();self._properties()

    def redo(self):
        if not self.redo_stack:return
        self.undo_stack.append(copy.deepcopy(self.layout));self.layout=self.redo_stack.pop()
        self.selected=None;self.dirty=True;self._render();self._properties()

    def pick_color(self,key):
        obj=self._get()
        if obj is None:return
        result=colorchooser.askcolor(obj[key],parent=self.window,title='Choose '+key)
        if result and result[1]:
            self._record();obj[key]=result[1].upper();self._render();self._properties()

    def choose_accent(self):
        result=colorchooser.askcolor(self.layout['accent'],parent=self.window,title='Accent color')
        if result and result[1]:
            self._record();self.layout['accent']=result[1].upper();self._render()

    def zoom(self,delta):
        self.scale=max(.5,min(1.5,round(self.scale+delta,2)));self._render()

    def change_paper(self,_=None):
        if self.page_var.get()==self.layout['page_size']:return
        self._record();pw,ph=PAGE_SIZES[self.page_var.get()]
        for o in self.layout['objects']:
            o['x']=min(o['x'],pw-o['w']) if o['w']<=pw else 0
            o['w']=min(o['w'],pw);o['y']=min(o['y'],ph-o['h']) if o['h']<=ph else 0
            o['h']=min(o['h'],ph)
        self.layout['page_size']=self.page_var.get();self._render();self._properties()

    def change_kind(self,_=None):
        if self.dirty and not messagebox.askyesno('Unsaved changes',
                    'Switch documents and discard unsaved changes?',parent=self.window):
            self.kind_var.set(self.kind);return
        self.kind=self.kind_var.get();self.layout=load(self.db,self.kind) or default_layout(self.kind)
        self.page_var.set(self.layout['page_size'])
        self.selected=None;self.undo_stack=[];self.redo_stack=[];self.dirty=False
        self._render();self._properties()
        self.message.set(self.kind+' design loaded.')

    def restore(self):
        if not messagebox.askyesno('Restore default design',f'Restore {self.kind} layout to the modern default? Changes will not be saved until you click Save design.',parent=self.window):return
        self._record();self.layout=default_layout(self.kind);self.page_var.set(self.layout['page_size'])
        self.selected=None;self._render();self._properties()

    def save(self):
        try:
            present={o['type'] for o in self.layout['objects']}
            missing=[label for kind,label in [('items','product line-item table'),('totals','document totals')] if kind not in present]
            if missing and not messagebox.askyesno('Important document fields missing',
                'This document design has no '+', '.join(missing)+'. It may omit required pricing information. Save anyway?',parent=self.window):return
            save(self.db,self.kind,self.layout);self.dirty=False
            self.message.set(self.kind+' visual design saved successfully. Future PDF exports will use this layout.')
            messagebox.showinfo('Template saved',self.kind+' design saved.',parent=self.window)
        except Exception as exc:messagebox.showerror('Cannot save layout',str(exc),parent=self.window)

    def preview(self):
        try:
            validate(self.kind,self.layout)
            path=self.storage/'template_previews'/f'{self.kind}_Visual_Preview_{uuid.uuid4().hex[:8]}.pdf'
            render(self.db,self.kind,0,path,layout=self.layout,preview=True)
            if os.name=='nt':os.startfile(str(path))
            else:
                import webbrowser
                webbrowser.open(path.as_uri())
            self.message.set('Preview PDF generated from the current unsaved design.')
        except Exception as exc:messagebox.showerror('Preview failed',str(exc),parent=self.window)

    def close(self):
        if self.dirty and not messagebox.askyesno('Unsaved design',
                'Close the designer without saving your changes?',parent=self.window):return
        self.window.destroy()


def open_visual_template_editor(parent,db,data_folder):
    return VisualTemplateEditor(parent,db,data_folder)
