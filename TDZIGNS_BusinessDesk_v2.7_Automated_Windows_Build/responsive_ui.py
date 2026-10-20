"""Responsive action toolbar: Tk grid wraps buttons instead of clipping them."""
import tkinter as tk
from tkinter import ttk

class ResponsiveToolbar(ttk.Frame):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,**kwargs)
        self._buttons=[]
        self._columns=0
        self.bind('<Configure>',self._reflow)

    def add_action(self,label,callback,accent=False):
        button=ttk.Button(self,text=label,command=callback,
                          style='Accent.TButton' if accent else 'TButton')
        self._buttons.append(button)
        if self.winfo_width()>=40:self._reflow()
        return button

    def _reflow(self,event=None):
        if not self.winfo_exists() or not self._buttons:return
        width=self.winfo_width()
        if width<40:return
        desired=min(340,max(160,max(b.winfo_reqwidth() for b in self._buttons)+16))
        columns=max(1,min(len(self._buttons),width//(desired+12)))
        if columns==self._columns:return
        for child in self._buttons:child.grid_forget()
        for index in range(max(self._columns,columns)):
            self.columnconfigure(index,weight=0,uniform='')
        for index in range(columns):self.columnconfigure(index,weight=1,uniform='actions')
        for index,button in enumerate(self._buttons):
            button.grid(row=index//columns,column=index%columns,sticky='ew',padx=4,pady=4)
        self._columns=columns


def scrollable_page(parent):
    """Create a flexible, vertically scrollable page for narrow/high-DPI screens."""
    holder=ttk.Frame(parent)
    holder.pack(fill='both',expand=True)
    holder.columnconfigure(0,weight=1)
    holder.rowconfigure(0,weight=1)
    canvas=tk.Canvas(holder,highlightthickness=0,borderwidth=0,bg='#F2F5F9')
    canvas.grid(row=0,column=0,sticky='nsew')
    scrollbar=ttk.Scrollbar(holder,orient='vertical',command=canvas.yview)
    scrollbar.grid(row=0,column=1,sticky='ns')
    canvas.configure(yscrollcommand=scrollbar.set)
    content=ttk.Frame(canvas,padding=(4,4))
    item=canvas.create_window(0,0,window=content,anchor='nw')
    content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    # Mouse wheel follows this page rather than scrolling unrelated windows.
    def wheel(event):
        if canvas.winfo_exists():
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
        return 'break'
    def enter(_):canvas.bind_all('<MouseWheel>',wheel)
    def leave(_):canvas.unbind_all('<MouseWheel>')
    holder.bind('<Enter>',enter)
    holder.bind('<Leave>',leave)
    holder.bind('<Destroy>',lambda e:canvas.unbind_all('<MouseWheel>') if e.widget==holder else None)
    return content
