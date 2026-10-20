"""BusinessDesk home hub: supplier/customer workflows and accessible quick actions.

This module deliberately delegates actions to the EXISTING BusinessDesk tab
callbacks. It does not duplicate accounting, inventory or PO business logic.
"""
import tkinter as tk
from tkinter import ttk

from modern_theme import BLUE, SLATE, TEXT, MUTED, CANVAS, WHITE, BORDER

PALE_BLUE = '#EDF4FF'
PALE_GREEN = '#EFF9F6'
GREEN = '#13816B'
SIDEBAR = '#FFFFFF'
UNAVAILABLE = '#A4ADBC'

# IDs are routed by BusinessDesk. Planned entries are visibly disabled and
# never pretend to record accounting or receiving transactions.
QUICK_LINKS = (
    ('SUPPLIERS', (
        ('Add supplier', 'supplier.add'),
        ('Import suppliers from Excel', 'supplier.import'),
        ('New purchase order', 'po.new'),
        ('Edit existing PO', 'po.edit'),
        ('Receive entire PO', 'po.receive'),
        ('Receive partial PO  ·  Planned', None),
        ('Record supplier payment  ·  Planned', None),
    )),
    ('CUSTOMERS', (
        ('Add new customer', 'customer.add'),
        ('Import customers from Excel', 'customer.import'),
        ('Edit customer information', 'customer.edit'),
        ('Customer-specific prices', 'customer.pricing'),
        ('Create new estimate', 'estimate.new'),
        ('Convert estimate to invoice', 'estimate.convert'),
        ('Receive invoice payment', 'invoice.payment'),
        ('Customer account credit  ·  Planned', None),
    )),
    ('PRODUCTS', (
        ('Add new product', 'product.add'),
        ('Import products from Excel', 'product.import'),
        ('Edit product list', 'product.edit'),
    )),
    ('MANAGEMENT', (
        ('Dashboard', 'dashboard'),
        ('Add an expense', 'expense.add'),
        ('Reports', 'reports'),
        ('Accounting', 'accounting'),
        ('Visual template designer', 'templates'),
        ('Administration', 'admin'),
        ('Settings / Updates', 'settings'),
    )),
)

# A narrow, logical identifier for every interactive workflow node.
SUPPLY_FLOW = (
    ('po.new', 'Create purchase\norder', 'Select a supplier and add items', 'PO'),
    ('po.receive', 'Receive full\norder', 'Update stock and accounting', 'IN'),
    (None, 'Partial receipt', 'Planned feature', '...'),
    (None, 'Supplier payment', 'Planned feature', '$'),
)
CUSTOMER_FLOW = (
    ('estimate.new', 'Create an\nestimate', 'Choose customer and products', 'EST'),
    ('estimate.convert', 'Convert estimate\nto invoice', 'Select an existing estimate', 'INV'),
    ('invoice.payment', 'Receive invoice\npayment', 'Select an unpaid invoice', '$'),
)


def install_styles(root):
    style=ttk.Style(root)
    style.configure('HomeSidebar.TFrame',background=SIDEBAR)
    style.configure('HomeSidebarHead.TLabel',background=SIDEBAR,foreground=SLATE,font=('Segoe UI',11,'bold'))
    style.configure('HomeGroup.TLabel',background=SIDEBAR,foreground=MUTED,font=('Segoe UI',8,'bold'))
    style.configure('HomeQuick.TButton',background=SIDEBAR,foreground=SLATE,font=('Segoe UI',9),
                    anchor='w',padding=(11,6),borderwidth=0,relief='flat')
    style.map('HomeQuick.TButton',background=[('active',PALE_BLUE)],foreground=[('active',BLUE)])
    style.configure('HomePlanned.TLabel',background=SIDEBAR,foreground=UNAVAILABLE,font=('Segoe UI',9))
    style.configure('HomeTitle.TLabel',background=CANVAS,foreground=SLATE,font=('Segoe UI',20,'bold'))
    style.configure('HomeHelp.TLabel',background=CANVAS,foreground=MUTED,font=('Segoe UI',10))
    style.configure('HomeCard.TFrame',background=WHITE,relief='flat')
    style.configure('HomeCardHeading.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',9))
    style.configure('HomeCardValue.TLabel',background=WHITE,foreground=SLATE,font=('Segoe UI',18,'bold'))
    style.configure('HomeCardDetail.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',8))


class HomeWorkspace:
    """Main Home tab, matching the sketch with a sidebar and two flowchart lanes."""
    def __init__(self, app, parent):
        self.app=app
        self.parent=parent
        install_styles(parent)
        self._canvas_commands={}
        self._hover_tag=None
        self._render_job=None
        self._build()

    def _build(self):
        shell=ttk.Frame(self.parent)
        shell.pack(fill='both',expand=True)
        sidebar=ttk.Frame(shell,style='HomeSidebar.TFrame',width=244)
        sidebar.pack(side='left',fill='y')
        sidebar.pack_propagate(False)
        ttk.Separator(shell,orient='vertical').pack(side='left',fill='y')
        self._sidebar(sidebar)

        work=ttk.Frame(shell,padding=(22,15))
        work.pack(side='left',fill='both',expand=True)
        head=ttk.Frame(work)
        head.pack(fill='x',pady=(0,13))
        text=ttk.Frame(head);text.pack(side='left',fill='x',expand=True)
        ttk.Label(text,text='Home workspace',style='HomeTitle.TLabel').pack(anchor='w')
        ttk.Label(text,text='Follow the supplier and customer workflows, or use the shortcuts on the left.',
                  style='HomeHelp.TLabel',wraplength=790).pack(anchor='w',pady=(3,0))
        ttk.Button(head,text='Dashboard  →',style='Accent.TButton',
                   command=lambda:self.app.navigate_home_action('dashboard')).pack(side='right',padx=(8,0))
        self._metrics(work)
        ttk.Label(work,text='BUSINESS WORKFLOWS',font=('Segoe UI',9,'bold'),
                  foreground=MUTED).pack(anchor='w',pady=(20,7))
        area=ttk.Frame(work)
        area.pack(fill='both',expand=True)
        vbar=ttk.Scrollbar(area,orient='vertical')
        vbar.pack(side='right',fill='y')
        hbar=ttk.Scrollbar(area,orient='horizontal')
        hbar.pack(side='bottom',fill='x')
        self._vbar=vbar
        self._hbar=hbar
        self.flow=tk.Canvas(area,bg=CANVAS,highlightthickness=0,bd=0,
                            yscrollcommand=vbar.set,xscrollcommand=hbar.set)
        self.flow.pack(side='left',fill='both',expand=True)
        vbar.configure(command=self.flow.yview)
        hbar.configure(command=self.flow.xview)
        self.flow.configure(scrollregion=(0,0,1020,445))
        self.flow.bind('<Configure>',self._resize_flow)
        self.flow.bind('<Destroy>',self._on_destroy)
        self.flow.bind('<Motion>',self._on_motion)
        self.flow.bind('<Leave>',lambda _:self._set_status('Click any blue or green workflow step to open its action.'))
        self.flow.bind('<Button-1>',self._on_flow_click)
        self.flow.bind('<MouseWheel>',lambda e:self.flow.yview_scroll(-1 if e.delta>0 else 1,'units'))
        self.flow.bind('<Button-4>',lambda _:self.flow.yview_scroll(-1,'units'))
        self.flow.bind('<Button-5>',lambda _:self.flow.yview_scroll(1,'units'))
        self.status=ttk.Label(work,text='Click any blue or green workflow step to open its action.',style='HomeHelp.TLabel')
        self.status.pack(anchor='w',pady=(4,0))
        self._render_job=self.flow.after_idle(self._redraw)

    def _sidebar(self,parent):
        ttk.Label(parent,text='QUICK ACCESS',style='HomeSidebarHead.TLabel').pack(anchor='w',padx=17,pady=(17,11))
        scroll_frame=ttk.Frame(parent,style='HomeSidebar.TFrame')
        scroll_frame.pack(fill='both',expand=True)
        scrollbar=ttk.Scrollbar(scroll_frame,orient='vertical')
        scrollbar.pack(side='right',fill='y')
        canvas=tk.Canvas(scroll_frame,bg=SIDEBAR,highlightthickness=0,bd=0,yscrollcommand=scrollbar.set)
        canvas.pack(side='left',fill='both',expand=True)
        scrollbar.configure(command=canvas.yview)
        content=ttk.Frame(canvas,style='HomeSidebar.TFrame')
        item=canvas.create_window(0,0,window=content,anchor='nw')
        content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        # Only scroll the sidebar when the pointer is over it.
        def scroll(event):
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
            return 'break'
        for group, links in QUICK_LINKS:
            ttk.Label(content,text=group,style='HomeGroup.TLabel').pack(anchor='w',padx=17,pady=(16,5))
            for title,action in links:
                if action is None:
                    ttk.Label(content,text=title,style='HomePlanned.TLabel',wraplength=195).pack(
                        anchor='w',fill='x',padx=20,pady=4)
                elif action in ('admin','templates') and self.app.user['role']!='admin':
                    continue
                else:
                    b=ttk.Button(content,text=title,style='HomeQuick.TButton',
                                 command=lambda a=action:self.app.navigate_home_action(a))
                    b.pack(fill='x',padx=(7,9),pady=1)
                    b.bind('<MouseWheel>',scroll)
        for obj in (canvas,content):obj.bind('<MouseWheel>',scroll)

    def _metrics(self,parent):
        db=self.app.db
        records=(
            ('Suppliers',db.execute('SELECT count(*) FROM suppliers').fetchone()[0],'Saved vendors'),
            ('Open purchase orders',db.execute("SELECT count(*) FROM purchase_orders WHERE status='Open'").fetchone()[0], 'Awaiting receiving'),
            ('Customers',db.execute('SELECT count(*) FROM customers').fetchone()[0],'Customer records'),
            ('Open estimates',db.execute("SELECT count(*) FROM documents WHERE kind='Estimate' AND status='Open'").fetchone()[0],'Ready to convert'),
        )
        strip=ttk.Frame(parent)
        strip.pack(fill='x')
        for i,(name,value,detail) in enumerate(records):
            card=ttk.Frame(strip,style='HomeCard.TFrame',padding=(14,12))
            card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 5,5),pady=0)
            ttk.Label(card,text=name,style='HomeCardHeading.TLabel').pack(anchor='w')
            ttk.Label(card,text=str(value),style='HomeCardValue.TLabel').pack(anchor='w',pady=(4,2))
            ttk.Label(card,text=detail,style='HomeCardDetail.TLabel').pack(anchor='w')
            strip.columnconfigure(i,weight=1,uniform='home_stats')

    def _on_destroy(self,event):
        if event.widget is self.flow and self._render_job:
            try:self.flow.after_cancel(self._render_job)
            except tk.TclError:pass
            self._render_job=None

    def _resize_flow(self,event):
        if self._render_job:
            self.flow.after_cancel(self._render_job)
        self._render_job=self.flow.after(65,self._redraw)

    def _set_status(self,text):
        if hasattr(self,'status') and self.status.winfo_exists():
            self.status.configure(text=text)

    def _redraw(self):
        self._render_job=None
        c=self.flow
        if not c.winfo_exists():return
        c.delete('all')
        self._canvas_commands={}
        width=max(970,c.winfo_width()-3)
        height=445
        # No unused scrollbars on a full-size desktop; enable scrolling when
        # users resize BusinessDesk or use a high-DPI, smaller display.
        if c.winfo_width()>=975:
            if self._hbar.winfo_manager():self._hbar.pack_forget()
        elif not self._hbar.winfo_manager():
            self._hbar.pack(side='bottom',fill='x')
        if c.winfo_height()>=height+3:
            if self._vbar.winfo_manager():self._vbar.pack_forget()
        elif not self._vbar.winfo_manager():
            self._vbar.pack(side='right',fill='y')
        c.configure(scrollregion=(0,0,width,height))
        self._lane(12,8,width-16,226,PALE_BLUE,'SUPPLIER / SUPPLY CHAIN',
                   'Order products, receive inventory, and track your supplier workflow.',BLUE)
        self._lane(12,235,width-16,437,PALE_GREEN,'CUSTOMER / SALES CHAIN',
                   'Start with an estimate, convert it to an invoice, and collect payment.',GREEN)
        # Nodes use a fixed minimum logical width; horizontal scrolling is
        # available instead of clipping nodes on a narrow display.
        left=width*0.053
        center=width*0.395
        right=width*0.775
        bw=188;bh=73
        top=93
        self._node(left,top,bw,bh,SUPPLY_FLOW[0],BLUE)
        self._node(center,top-21,bw,bh,SUPPLY_FLOW[1],BLUE)
        self._node(center,top+55,bw,bh,SUPPLY_FLOW[2],BLUE)
        self._node(right,top,bw,bh,SUPPLY_FLOW[3],BLUE)
        # Two branching options then merge to supplier settlement.
        self._arrow(left+bw,top+bh/2,center-14,top+bh/2,BLUE)
        self._arrow(center-14,top+bh/2,center,top-21+bh/2,BLUE)
        self._arrow(center-14,top+bh/2,center,top+55+bh/2,BLUE)
        self._arrow(center+bw,top-21+bh/2,right-20,top+bh/2,BLUE)
        self._arrow(center+bw,top+55+bh/2,right-20,top+bh/2,BLUE)
        self._arrow(right-20,top+bh/2,right,top+bh/2,BLUE)
        # Customer flow: estimate -> invoice -> payment.
        y=333
        self._node(left,y,bw,bh,CUSTOMER_FLOW[0],GREEN)
        self._node(center,y,bw,bh,CUSTOMER_FLOW[1],GREEN)
        self._node(right,y,bw,bh,CUSTOMER_FLOW[2],GREEN)
        self._arrow(left+bw,y+bh/2,center,y+bh/2,GREEN)
        self._arrow(center+bw,y+bh/2,right,y+bh/2,GREEN)
        c.tag_raise('workflow_node')
        c.tag_raise('workflow_text')

    def _lane(self,x1,y1,x2,y2,fill,heading,detail,color):
        c=self.flow
        c.create_rectangle(x1,y1,x2,y2,fill=fill,outline=BORDER,width=1)
        c.create_rectangle(x1,y1,x1+5,y2,fill=color,outline=color)
        c.create_text(x1+21,y1+27,text=heading,anchor='w',fill=color,font=('Segoe UI',12,'bold'))
        c.create_text(x1+21,y1+51,text=detail,anchor='w',fill=MUTED,font=('Segoe UI',9))

    def _node(self,x,y,w,h,info,color):
        action,title,description,token=info
        active=action is not None
        outline=color if active else '#BBC5D0'
        fill=WHITE if active else '#F4F6F9'
        c=self.flow
        tag=f'action:{action}' if active else 'unavailable'
        if active:self._canvas_commands[action]=description
        shadow='shadow:'+str(x)+':'+str(y)
        c.create_rectangle(x+3,y+4,x+w+3,y+h+4,fill='#DEE6F0',outline='',tags=('workflow_node',))
        c.create_rectangle(x,y,x+w,y+h,fill=fill,outline=outline,width=2 if active else 1,
                           tags=('workflow_node',tag))
        c.create_rectangle(x,y,x+6,y+h,fill=outline,outline=outline,tags=('workflow_node',tag))
        c.create_text(x+18,y+26,text=title,anchor='w',justify='left',font=('Segoe UI',10,'bold'),
                      fill=SLATE if active else UNAVAILABLE,tags=('workflow_text',tag))
        c.create_text(x+18,y+h-13,text=description,anchor='w',font=('Segoe UI',8),
                      fill=MUTED if active else UNAVAILABLE,tags=('workflow_text',tag))
        if not active:
            c.create_text(x+w-14,y+11,text='SOON',anchor='e',fill=UNAVAILABLE,
                          font=('Segoe UI',7,'bold'),tags=('workflow_text',tag))

    def _arrow(self,x1,y1,x2,y2,color):
        c=self.flow
        if x2<=x1:return
        c.create_line(x1+2,y1,x2-5,y2,fill=color,width=2,arrow='last',arrowshape=(10,12,5),
                      smooth=abs(y2-y1)>5,capstyle=tk.ROUND)

    def _action_under_pointer(self):
        current=self.flow.find_withtag('current')
        if not current:return None
        for tag in self.flow.gettags(current[0]):
            if tag.startswith('action:'):
                action=tag[7:]
                if action in self._canvas_commands:return action
        return None

    def _on_motion(self,event):
        action=self._action_under_pointer()
        self.flow.configure(cursor='hand2' if action else '')
        if action!=self._hover_tag:
            self._hover_tag=action
            self._set_status(self._canvas_commands.get(action,'Planned step — not yet available.' if action is None else ''))

    def _on_flow_click(self,event):
        action=self._action_under_pointer()
        if action:
            self.app.navigate_home_action(action)
