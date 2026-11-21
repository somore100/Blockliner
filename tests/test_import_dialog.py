"""The Import Code dialog: its buttons are always reachable (even in a small window) and 'Open as nodes' opens a new tab of nodes. Scripted UI test (run under Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tkinter import messagebox
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def buttons(w):
    out = []
    for c in w.winfo_children():
        out += ([c] if c.winfo_class() == "Button" else []) + buttons(c)
    return out

def main():
    messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        app.view_mode = "files"
        dlg = app.open_code_to_blocks_dialog()
        dlg.geometry("500x300")
        dlg.update()
        texts = {b.cget("text"): b for b in buttons(dlg)}
        check("the blocks and nodes buttons exist", any("blocks" in t for t in texts) and any("nodes" in t for t in texts))
        bottom = dlg.winfo_height()
        check("every button is inside the window", all(b.winfo_rooty() + b.winfo_height() <= dlg.winfo_rooty() + bottom for b in texts.values()))
        text = [c for c in dlg.winfo_children() if c.winfo_class() == "Text"][0]
        text.insert("1.0", "import os\n\nclass A:\n    def f(self):\n        return 1\n\n    def g(self):\n        return 2\n")
        before = len(app.tabs)
        next(b for t, b in texts.items() if "nodes" in t).invoke()
        check("a new tab opened", len(app.tabs) == before + 1)
        names = [n["name"] for n in app.tabs[-1]["nodes"]]
        check(f"it holds imports and the class ({names})", names == ["imports", "A"])
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
