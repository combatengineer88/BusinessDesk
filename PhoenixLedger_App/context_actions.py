"""Reusable, keyboard-accessible Treeview right-click quick actions.

Actions use the same callbacks as the existing toolbar, including its existing
validation, dialogs, stock updates and accounting behavior.
"""
import tkinter as tk
from tkinter import ttk


def install_context_menu(tree, actions, safe=None):
    """Bind right-click and Menu/Shift+F10 keys to row-aware actions.

    actions is a list of (label, callback, needs_selection) tuples; None is a
    separator. Returning the Menu allows tests and callers to inspect it.
    """
    menu=tk.Menu(tree,tearoff=0,relief='solid',bd=1,
                 activebackground='#E7EFFB',activeforeground='#173B73',
                 background='#FFFFFF',foreground='#243247',font=('Segoe UI',10))
    def run(callback):
        if safe is not None:
            safe(callback)
        else:
            callback()
    for action in actions:
        if action is None:
            menu.add_separator()
            continue
        label,callback,*require=action
        needs_selection=bool(require[0]) if require else True
        menu.add_command(label=label,command=lambda fn=callback:run(fn))
    def sync_states():
        selected=bool(tree.selection())
        for index, action in enumerate(actions):
            if action is None:continue
            needs_selection=bool(action[2]) if len(action)>2 else True
            menu.entryconfigure(index,state='normal' if selected or not needs_selection else 'disabled')
    def popup(event=None):
        if event is not None:
            item=tree.identify_row(event.y)
            if item:
                if item not in tree.selection():
                    tree.selection_set(item)
                tree.focus(item)
            else:
                tree.selection_remove(tree.selection())
        sync_states()
        try:
            if event is not None:
                menu.tk_popup(event.x_root,event.y_root)
            else:
                focus=tree.focus()
                bbox=tree.bbox(focus) if focus else None
                x=tree.winfo_rootx()+(bbox[0]+12 if bbox else 24)
                y=tree.winfo_rooty()+(bbox[1]+bbox[3] if bbox else 24)
                menu.tk_popup(x,y)
        finally:
            menu.grab_release()
        return 'break'
    tree.bind('<Button-3>',popup,add='+')
    tree.bind('<Shift-F10>',lambda event:popup(),add='+')
    tree.bind('<Menu>',lambda event:popup(),add='+')
    tree._phoenix_context_menu=menu  # Keep the menu alive with the Treeview.
    return menu
