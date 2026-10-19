"""Tkinter document template editor with independent estimate / invoice / PO tabs."""

import os
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

from document_templates import (KINDS, LAYOUTS, FONTS, PAGE_SIZES, LOGO_POSITIONS,
                                CHECK_FIELDS, defaults, validate, load_template,
                                save_template, reset_template, render_document)


class TemplateEditor:
    """A settings editor; it does not alter existing business/accounting records."""
    def __init__(self, parent, db, preview_directory):
        self.db = db
        self.preview_directory = Path(preview_directory)
        self.window = tk.Toplevel(parent)
        self.window.title('Customize BusinessDesk document templates')
        self.window.transient(parent)
        self.window.geometry('850x725')
        self.window.minsize(700,540)
        self.window.grab_set()
        header=ttk.Frame(self.window,padding=12);header.pack(fill='x')
        ttk.Label(header,text='Document Template Designer',font=('Segoe UI',17,'bold')).pack(anchor='w')
        ttk.Label(header,text='Customize each document type independently. Preview changes before saving. Business data and totals are unchanged.',
                  wraplength=790).pack(anchor='w',pady=4)
        self.tabs=ttk.Notebook(self.window);self.tabs.pack(fill='both',expand=True,padx=14,pady=5)
        self.inputs={}
        for kind in KINDS:
            panel=ttk.Frame(self.tabs)
            self.tabs.add(panel,text={'Estimate':'Estimates','Invoice':'Invoices','PO':'Purchase Orders'}[kind])
            self.build_tab(panel,kind)
        actions=ttk.Frame(self.window,padding=12);actions.pack(fill='x')
        self.status=tk.StringVar(value='Choose a document type and edit its settings.')
        ttk.Label(actions,textvariable=self.status).pack(side='left',fill='x',expand=True)
        ttk.Button(actions,text='Close',command=self.window.destroy).pack(side='right')
        ttk.Button(actions,text='Restore defaults',command=self.reset_current).pack(side='right',padx=6)
        ttk.Button(actions,text='Preview PDF',command=self.preview_current).pack(side='right',padx=6)
        ttk.Button(actions,text='Save template',command=self.save_current).pack(side='right',padx=6)

    def _current_kind(self):
        return KINDS[self.tabs.index(self.tabs.select())]

    def build_tab(self, frame, kind):
        canvas=tk.Canvas(frame,highlightthickness=0)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        content=ttk.Frame(canvas,padding=12)
        embedded=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(embedded,width=event.width))
        values=load_template(self.db,kind)
        widgets={};self.inputs[kind]=widgets
        current_row=0

        def heading(text):
            nonlocal current_row
            ttk.Label(content,text=text,font=('Segoe UI',11,'bold')).grid(row=current_row,column=0,columnspan=3,sticky='w',pady=(16,7))
            current_row+=1

        def input_field(name,label,option=None):
            nonlocal current_row
            var=tk.StringVar(value=values[name]);widgets[name]=var
            ttk.Label(content,text=label).grid(row=current_row,column=0,sticky='w',padx=(0,14),pady=4)
            if option:
                entry=ttk.Combobox(content,textvariable=var,values=option,state='readonly',width=35)
            else:entry=ttk.Entry(content,textvariable=var,width=45)
            entry.grid(row=current_row,column=1,sticky='ew',pady=4)
            current_row+=1
            return var

        heading('Layout and appearance')
        input_field('layout','Layout preset',LAYOUTS)
        input_field('font','Font',FONTS)
        input_field('page_size','Paper size',PAGE_SIZES)
        accent=input_field('accent_color','Accent color (#RRGGBB)')
        ttk.Button(content,text='Choose color…',command=lambda:self.pick_color(accent)).grid(row=current_row-1,column=2,padx=8)
        input_field('logo_position','Logo position',LOGO_POSITIONS)
        heading('Headings and labels')
        input_field('heading','Document heading')
        input_field('tagline','Optional subtitle')
        input_field('recipient_label','Recipient label')
        input_field('notes_heading','Notes section label')
        input_field('terms_heading','Terms section label')
        heading('Line-item table headings')
        input_field('label_item','Product / item')
        input_field('label_quantity','Quantity')
        input_field('label_rate','Price / cost')
        input_field('label_total','Line total')
        heading('Visible sections')
        labels={'show_logo':'Include company logo','show_contact':'Include business address / phone / email',
                'show_address':'Include customer / supplier address', 'show_notes':'Include saved document notes',
                'show_zero_tax':'Show zero-tax row (not applicable to POs)',
                'show_page_numbers':'Show page numbers'}
        for key in CHECK_FIELDS:
            var=tk.BooleanVar(value=values[key]);widgets[key]=var
            control=ttk.Checkbutton(content,text=labels[key],variable=var)
            control.grid(row=current_row,column=0,columnspan=3,sticky='w',pady=3)
            current_row+=1
        heading('Optional text')
        for key,label,lines in [('terms','Terms & conditions',4),('footer','Footer text (each page)',2)]:
            ttk.Label(content,text=label).grid(row=current_row,column=0,sticky='nw',pady=6)
            text=tk.Text(content,height=lines,width=52,wrap='word',font=('Segoe UI',10))
            text.insert('1.0',values[key]);text.grid(row=current_row,column=1,columnspan=2,sticky='ew',pady=6)
            widgets[key]=text
            current_row+=1
        content.columnconfigure(1,weight=1)
        ttk.Label(content,text='Previews use sample entries and do not create estimates, invoices, or purchase orders.',
                  foreground='#666666').grid(row=current_row,column=0,columnspan=3,sticky='w',pady=12)

    def pick_color(self,variable):
        color=colorchooser.askcolor(color=variable.get(),parent=self.window,title='Document accent color')
        if color and color[1]:variable.set(color[1])

    def gather(self,kind):
        result={}
        for key,var in self.inputs[kind].items():
            result[key]=var.get('1.0','end-1c').strip() if isinstance(var,tk.Text) else var.get()
        return validate(kind,result)

    def replace_inputs(self,kind,new):
        for key,var in self.inputs[kind].items():
            if isinstance(var,tk.Text):
                var.delete('1.0','end');var.insert('1.0',new[key])
            else:var.set(new[key])

    def save_current(self):
        kind=self._current_kind()
        try:
            conf=self.gather(kind)
            save_template(self.db,kind,conf)
            self.status.set(f'{kind} template saved. Newly exported PDFs will use these settings.')
            messagebox.showinfo('Template saved',f'{kind} template saved successfully.',parent=self.window)
        except Exception as exc:messagebox.showerror('Invalid template',str(exc),parent=self.window)

    def reset_current(self):
        kind=self._current_kind()
        if not messagebox.askyesno('Restore default template',f'Reset {kind} to its default template and save this change?',parent=self.window):return
        try:
            reset_template(self.db,kind)
            self.replace_inputs(kind,defaults(kind))
            self.status.set(f'{kind} template restored to defaults.')
        except Exception as exc:messagebox.showerror('Reset failed',str(exc),parent=self.window)

    def preview_current(self):
        kind=self._current_kind()
        try:
            config=self.gather(kind)
            self.preview_directory.mkdir(parents=True,exist_ok=True)
            file=self.preview_directory/f'BusinessDesk_{kind}_Template_Preview_{uuid.uuid4().hex[:8]}.pdf'
            render_document(self.db,kind,0,file,template_override=config,preview=True)
            if os.name=='nt':os.startfile(str(file))
            else:
                import webbrowser
                webbrowser.open(file.as_uri())
            self.status.set(f'{kind} sample PDF opened for preview.')
        except Exception as exc:messagebox.showerror('Preview failed',str(exc),parent=self.window)


def open_template_editor(parent,db,data_folder):
    return TemplateEditor(parent,db,Path(data_folder)/'template_previews')
