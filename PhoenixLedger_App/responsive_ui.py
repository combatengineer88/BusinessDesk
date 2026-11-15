"""Responsive action toolbar with compact overflow instead of clipped controls."""
import tkinter as tk
from tkinter import ttk

class ResponsiveToolbar(ttk.Frame):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,**kwargs)
        self._buttons=[]
        self._actions=[]
        self._columns=0
        self._more_menu=tk.Menu(self,tearoff=False)
        self._more_button=ttk.Button(self,text='More actions ▾',command=self._open_more)
        self._cached_shape=None
        self.bind('<Configure>',self._reflow,add='+')
        self._host_root=self.winfo_toplevel()
        self._root_bind_id=self._host_root.bind('<Configure>',self._root_reflow,add='+')
        self.bind('<Destroy>',self._unbind_root,add='+')

    def _unbind_root(self,event):
        if event.widget is self and self._host_root.winfo_exists():
            self._host_root.unbind('<Configure>',self._root_bind_id)

    def add_action(self,label,callback,accent=False):
        button=ttk.Button(self,text=label,command=callback,
                          style='Accent.TButton' if accent else 'TButton')
        self._buttons.append(button)
        self._actions.append((label,callback))
        self.after_idle(self._reflow)
        return button

    def _root_reflow(self,event):
        if self.winfo_exists() and event.widget is self._host_root:
            self.after_idle(self._reflow)

    def _open_more(self):
        self._more_menu.tk_popup(self._more_button.winfo_rootx(),
                                 self._more_button.winfo_rooty()+self._more_button.winfo_height())
        self._more_menu.grab_release()

    def _reflow(self,event=None):
        if not self.winfo_exists() or not self._buttons:return
        width=self.winfo_width()
        if width<100:return
        top=self.winfo_toplevel()
        available_height=top.winfo_height()
        max_rows=2 if available_height<750 else 3
        desired=min(255,max(145,max(b.winfo_reqwidth() for b in self._buttons)+6))
        columns=max(1,min(len(self._buttons),width//(desired+8)))
        max_shown=columns*max_rows
        overflow=len(self._buttons)>max_shown
        if overflow:max_shown-=1  # Reserve a visible More actions button.
        shape=(columns,max_shown,overflow)
        if shape==self._cached_shape:return
        self._cached_shape=shape
        for button in self._buttons:button.grid_forget()
        self._more_button.grid_forget()
        for col in range(max(self._columns,columns)):
            self.columnconfigure(col,weight=0,uniform='')
        for col in range(columns):self.columnconfigure(col,weight=1,uniform='phoenix_actions')
        for index,button in enumerate(self._buttons[:max_shown]):
            button.grid(row=index//columns,column=index%columns,sticky='ew',padx=3,pady=3)
        if overflow:
            self._more_menu.delete(0,'end')
            for label,callback in self._actions[max_shown:]:
                self._more_menu.add_command(label=label,command=callback)
            self._more_button.grid(row=max_shown//columns,column=max_shown%columns,
                                   sticky='ew',padx=3,pady=3)
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
