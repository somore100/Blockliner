"""File > Apply AI Changes: paste, review, apply as one undoable step. Scripted UI test (run under Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from tkinter import messagebox
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

SRC = "import os\n\ndef greet(name):\n    print('hi', name)\n    return name\n\ndef main():\n    greet('x')\n"
CHAT = '''=== edit: greet
<<<<<<< SEARCH
print('hi', name)
=======
print('hello', name)
>>>>>>> REPLACE

=== new: bye
def bye():
    print('bye')

=== edit: nothere
<<<<<<< SEARCH
x
=======
y
>>>>>>> REPLACE
'''

def toplevels(app):
    return [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]

def main():
    messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        app.open_text_as_nodes(SRC)
        tab = app.tabs[app.active_tab_index]
        before = app.generate_code_for_tab(tab, "python")
        dlg = app.open_changes_dialog()
        dlg._changes_box.insert("1.0", CHAT)
        dlg._changes_preview()
        rev = toplevels(app)[-1]
        ok = [c.ok for c in rev._changes]
        check(f"three changes, the unknown node can't apply ({ok})", ok == [True, True, False])
        check("the bad one is not ticked", [v.get() for v in rev._change_vars] == [True, True, False])
        rev._apply()
        tab = app.tabs[app.active_tab_index]
        code = app.generate_code_for_tab(tab, "python")
        check("the edit is in the code", "print('hello', name)" in code and "print('hi'" not in code)
        check("the new node is added", "def bye():" in code and any(n["name"] == "bye" for n in tab["nodes"]))
        check("other code is untouched", "greet('x')" in code and "import os" in code)
        check("one Ctrl+Z undoes it all", app.undo_project())
        tab = app.tabs[app.active_tab_index]
        check("undo restores the code", app.generate_code_for_tab(tab, "python") == before)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
