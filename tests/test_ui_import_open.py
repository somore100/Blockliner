"""A hand-written tkinter program opens in the designer: window as a UI node, functions as nodes, handlers linked, and
the generated program still works. Scripted UI test (run under Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from tkinter import messagebox
import ui_node
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

SRC = '''import tkinter as tk

expression = ""

def press(n):
    global expression
    expression += str(n)
    display.config(text=expression)

def clear():
    global expression
    expression = ""
    display.config(text="0")

root = tk.Tk()
root.title('Calc')
display = tk.Label(root, text='0', bg='black', fg='white')
display.grid(row=0, column=0, columnspan=2)
clr = tk.Button(root, text='C', command=clear, width=5)
clr.grid(row=1, column=0)
one = tk.Button(root, text='1', command=lambda: press(1))
one.grid(row=1, column=1)
root.mainloop()
'''

def main():
    asked = []
    messagebox.showinfo = lambda *a, **k: asked.append(a)
    messagebox.askyesno = lambda *a, **k: True
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        check("the code is offered to the designer", app.open_text_as_nodes(SRC) is None and len(app.tabs) == 2)
        tab = app.tabs[app.active_tab_index]
        nodes = tab["nodes"]
        names = [(n["name"], ui_node.is_ui_node(n)) for n in nodes]
        check(f"imports, variable, functions and the window ({names})", [n for n, _u in names].count("app_window") == 1 and ("press", False) in names and ("clear", False) in names)
        win = next(n for n in nodes if ui_node.is_ui_node(n))
        check("the window has 3 widgets", ui_node.widget_count(win) == 3)
        clr_w = next(w for w in win["ui"]["root"]["children"] if w["name"] == "clr")
        clear_id = next(n["id"] for n in nodes if n["name"] == "clear")
        check("command=clear is linked to the clear node", clr_w["events"].get("command") == clear_id)
        one_w = next(w for w in win["ui"]["root"]["children"] if w["name"] == "one")
        check("a lambda stays as written", one_w["extra"].get("command") == "lambda: press(1)")
        code = app.generate_code_for_tab(tab, "python")
        check("the generated program is valid", compile(code, "gen", "exec") is not None)
        # run it: build the window, press a button's handler, read the label
        ns = {}
        runnable = code.replace("ui.root.mainloop()", "ui.root.update()")
        exec(compile(runnable, "gen", "exec"), ns)
        ns["press"](7)
        ns["ui"].root.update()
        check("a handler that uses a widget by name still works", ns["ui"].display.cget("text") == "7")
        ns["ui"].clr.invoke()
        check("a linked button runs its function", ns["ui"].display.cget("text") == "0")
        ns["ui"].root.destroy()
        n_tabs = len(app.tabs)
        check("a program with no window is not taken", app.open_text_as_ui("x = 1\n", show_problems=False) is False and len(app.tabs) == n_tabs)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
