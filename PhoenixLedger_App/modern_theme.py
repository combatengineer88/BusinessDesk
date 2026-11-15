"""Modern professional PhoenixLedger palette and ttk component styling."""
from tkinter import ttk


def _rounded_button_image(root, colors, radius=8):
    """Nine-slice raster with a restrained drop shadow and bevel highlight."""
    from PIL import Image, ImageDraw, ImageTk
    w,h=72,27
    image=Image.new('RGBA',(w,h),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    shadow=colors[2]
    draw.rounded_rectangle((1,3,w-2,h-1),radius=radius,fill=shadow)
    draw.rounded_rectangle((1,0,w-2,h-4),radius=radius,fill=colors[1])
    draw.rounded_rectangle((2,1,w-3,h-5),radius=radius-1,fill=colors[0])
    draw.line((10,2,w-11,2),fill=(255,255,255,120),width=1)
    return ImageTk.PhotoImage(image,master=root)


def _install_rounded_buttons(root,s):
    """Use Tk nine-slice image elements so *all* ttk buttons remain native,
    responsive, keyboard accessible, and rounded (not just toolbar buttons).
    """
    if getattr(root,'_phoenix_button_art',None):return
    from PIL import Image,ImageDraw,ImageTk
    variants={
        'default':(('#FFFFFF','#CED8E5','#B2C2D4'),
                   ('#F3F8FF','#9DBCEB','#A6BBDD'),
                   ('#DBE7FA','#9AB6DA','#D7E2EE'),
                   ('#EEF1F5','#D6DFE9','#D2D9E3')),
        'accent':(('#3277EC','#1D56B8','#B1BCD0'),
                  ('#4589F7','#2362CB','#B2C4DD'),
                  ('#1F56BA','#153A85','#D3DDEB'),
                  ('#A2B6D7','#8A9FBD','#D4DFEB')),
    }
    art=[]
    for kind, palettes in variants.items():
        imgs=[_rounded_button_image(root,colors) for colors in palettes]
        art.extend(imgs)
        element='Phoenix'+kind.title()+'.border'
        if element not in s.element_names():
            s.element_create(element,'image',imgs[0],
                ('disabled',imgs[3]), ('pressed',imgs[2]), ('active',imgs[1]),
                border=(10,8,10,10),sticky='nsew')
        layout=[(element,{'sticky':'nsew','children':[
            ('Button.padding',{'sticky':'nsew','children':[
                ('Button.label',{'sticky':'nsew'})]})]})]
        s.layout('Accent.TButton' if kind=='accent' else 'TButton',layout)
    root._phoenix_button_art=art


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
    s.configure('TButton',font=('Segoe UI',9,'bold'),padding=(12,5),background=WHITE,
                foreground=SLATE,borderwidth=0,relief='flat',bordercolor=BORDER,focuscolor=WHITE)
    s.map('TButton',background=[('active','#EAF0F9'),('pressed','#DDE6F2')],
          foreground=[('disabled','#93A1B3')])
    s.configure('Accent.TButton',background=BLUE,foreground=WHITE,padding=(13,5),bordercolor=BLUE)
    s.map('Accent.TButton',background=[('active','#1D4ED8'),('pressed','#1E40AF')],foreground=[('active',WHITE)])
    s.configure('Tool.TButton',font=('Segoe UI',9),anchor='w',padding=(10,5),background=WHITE)
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
    # Pillow is already part of the packaged app; use native ttk fallback
    # rather than preventing startup if rendering support is unavailable.
    try:
        _install_rounded_buttons(root,s)
    except (ImportError,RuntimeError,ValueError) as exc:
        root._phoenix_button_theme_warning=str(exc)
    return s
