"""Modern professional PhoenixLedger palette and ttk component styling."""
from tkinter import ttk

SLATE='#17263C'
DEEP='#0F1C2F'
BLUE='#2563EB'
TEXT='#243247'
MUTED='#64748B'
CANVAS='#F2F5F9'
WHITE='#FFFFFF'
BORDER='#DCE4EF'


def apply(root):
    s=ttk.Style(root)
    if 'clam' in s.theme_names():s.theme_use('clam')
    root.configure(background=CANVAS)
    s.configure('.',font=('Segoe UI',10),background=CANVAS,foreground=TEXT)
    s.configure('TFrame',background=CANVAS)
    s.configure('Surface.TFrame',background=WHITE)
    s.configure('TLabel',background=CANVAS,foreground=TEXT,font=('Segoe UI',10))
    s.configure('PageTitle.TLabel',background=WHITE,foreground=SLATE,font=('Segoe UI',18,'bold'))
    s.configure('Subtle.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',9))
    s.configure('Property.TLabel',background=WHITE,foreground=SLATE,font=('Segoe UI',9))
    s.configure('SideHeading.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',9,'bold'))
    s.configure('Header.TFrame',background=SLATE)
    s.configure('HeaderIcon.TLabel',background=SLATE,padding=0,borderwidth=0,relief='flat')
    s.configure('HeaderTitle.TLabel',background=SLATE,foreground=WHITE,font=('Segoe UI',17,'bold'))
    s.configure('HeaderInfo.TLabel',background=SLATE,foreground='#B9C7D9',font=('Segoe UI',10))
    s.configure('Card.TFrame',background=WHITE,relief='solid',borderwidth=1)
    s.configure('CardTitle.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',10))
    s.configure('CardValue.TLabel',background=WHITE,foreground=SLATE,font=('Segoe UI',22,'bold'))
    s.configure('CardCaption.TLabel',background=WHITE,foreground=MUTED,font=('Segoe UI',9))
    s.configure('Section.TLabel',foreground=SLATE,font=('Segoe UI',14,'bold'))
    s.configure('TButton',font=('Segoe UI',9,'bold'),padding=(13,8),background=WHITE,
                foreground=SLATE,borderwidth=1,relief='flat',bordercolor=BORDER,focuscolor=WHITE)
    s.map('TButton',background=[('active','#EAF0F9'),('pressed','#DDE6F2')],
          foreground=[('disabled','#93A1B3')])
    s.configure('Accent.TButton',background=BLUE,foreground=WHITE,padding=(14,9),bordercolor=BLUE)
    s.map('Accent.TButton',background=[('active','#1D4ED8'),('pressed','#1E40AF')],foreground=[('active',WHITE)])
    s.configure('Tool.TButton',font=('Segoe UI',9),anchor='w',padding=(10,6),background=WHITE)
    s.map('Tool.TButton',background=[('active','#EAF0F9')])
    s.configure('TNotebook',background=CANVAS,borderwidth=0,tabmargins=(2,6,2,0))
    s.configure('TNotebook.Tab',font=('Segoe UI',10,'bold'),padding=(12,9),background='#E4EAF2',
                foreground=MUTED,focuscolor=CANVAS)
    s.map('TNotebook.Tab',background=[('selected',WHITE),('active','#D5E3F8')],
          foreground=[('selected',BLUE),('active',SLATE)])
    s.configure('Treeview',background=WHITE,foreground=TEXT,fieldbackground=WHITE,
                rowheight=32,bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,relief='flat',
                font=('Segoe UI',9))
    s.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),background='#E9EFF6',foreground=SLATE,
                relief='flat',padding=(8,10))
    s.map('Treeview',background=[('selected','#DCEAFF')],foreground=[('selected','#10366F')])
    s.map('Treeview.Heading',background=[('active','#DCE8F7')])
    s.configure('TEntry',padding=(7,7),fieldbackground=WHITE,bordercolor=BORDER,lightcolor=BORDER)
    s.configure('TCombobox',padding=(6,7),fieldbackground=WHITE,bordercolor=BORDER,lightcolor=BORDER)
    s.configure('TCheckbutton',padding=4,background=CANVAS,foreground=TEXT)
    s.configure('TSeparator',background=BORDER)
    return s
