"""Login and signed-in recovery-code interactions using only Tkinter."""
import tkinter as tk
from tkinter import ttk, messagebox
from account_recovery import generate_code, has_code, lookup_by_code, reset_with_code


def show_code(parent, db, user_id):
    if not messagebox.askyesno('Generate recovery code',
       'This replaces any previous recovery code for this user. Continue?',parent=parent):
        return None
    code=generate_code(db,user_id)
    win=tk.Toplevel(parent);win.title('PhoenixLedger recovery code')
    win.transient(parent);win.grab_set();win.resizable(False,False)
    body=ttk.Frame(win,padding=22);body.pack(fill='both')
    ttk.Label(body,text='Save this one-time recovery code',font=('Segoe UI',13,'bold')).pack(anchor='w')
    ttk.Label(body,text='Keep it somewhere private. It is shown only once. The next time you use it, it becomes invalid.',
              wraplength=440).pack(anchor='w',pady=(8,12))
    field=ttk.Entry(body,width=48,font=('Consolas',11));field.insert(0,code)
    field.configure(state='readonly');field.pack(fill='x')
    def copy_code():
        win.clipboard_clear();win.clipboard_append(code);win.update()
        messagebox.showinfo('Copied','Recovery code copied. Store it in a secure location.',parent=win)
    row=ttk.Frame(body);row.pack(fill='x',pady=(14,0))
    ttk.Button(row,text='Copy recovery code',command=copy_code).pack(side='left')
    ttk.Button(row,text='I saved this code',command=win.destroy).pack(side='right')
    win.wait_window()
    return True


def forgot_account(parent, db, data_folder, on_success):
    win=tk.Toplevel(parent);win.title('PhoenixLedger | Account recovery')
    win.transient(parent);win.grab_set();win.resizable(False,False)
    outer=ttk.Frame(win,padding=22);outer.pack(fill='both')
    ttk.Label(outer,text='Recover your account',font=('Segoe UI',15,'bold')).pack(anchor='w')
    ttk.Label(outer,text='Enter a recovery code saved from a previous sign-in. The code identifies your username. '
              'After resetting your password, the code cannot be reused.',wraplength=440).pack(anchor='w',pady=(8,12))
    ttk.Label(outer,text='Recovery code').pack(anchor='w')
    code=tk.StringVar();ttk.Entry(outer,textvariable=code,width=48).pack(fill='x',pady=(2,9))
    ttk.Label(outer,text='New password (at least 10 characters)').pack(anchor='w')
    pw=tk.StringVar();ttk.Entry(outer,textvariable=pw,show='*',width=48).pack(fill='x',pady=(2,9))
    ttk.Label(outer,text='Confirm new password').pack(anchor='w')
    confirm=tk.StringVar();ttk.Entry(outer,textvariable=confirm,show='*',width=48).pack(fill='x',pady=(2,9))
    def apply():
        try:
            if pw.get()!=confirm.get():raise ValueError('Passwords do not match.')
            username,backup=reset_with_code(db,code.get(),pw.get(),data_folder)
            win.destroy()
            messagebox.showinfo('Account recovered',f'Username: {username}\n\n'
                f'Your password has been reset.\nDatabase backup: {backup}\n\n'
                'Sign in using the new password.',parent=parent)
            on_success(username)
        except Exception as error:
            messagebox.showerror('Could not recover account',str(error),parent=win)
    buttons=ttk.Frame(outer);buttons.pack(fill='x',pady=(12,0))
    ttk.Button(buttons,text='Reset password',command=apply).pack(side='left')
    ttk.Button(buttons,text='Cancel',command=win.destroy).pack(side='right')
    return win
