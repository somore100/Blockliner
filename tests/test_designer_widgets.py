"""Scripted UI test (run under Xvfb): every widget of the tkinter UI library can be added in the real designer and drawn."""
import os, sys, time
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI
import ui_node

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def settle(app, sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        app.update_idletasks(); app.update(); time.sleep(0.01)

def main():
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1300x800+0+0")
    app.ask_ui_pack = lambda packs: packs[0]
    try:
        settle(app)
        pack = app.ui_pack_for("python")
        node = app.create_starter_node("ui", (80, 80))
        app.open_node(node["id"])
        settle(app)
        ed = app.designer_editor
        for typ in pack.widgets:
            if typ in pack.root_types:
                continue
            try:
                ed.state["sel"] = ui_node.load_tree(node, pack).root["id"]     # add to the window
                ed._dz_add_type(typ)
                settle(app, 0.05)
                ok = True
            except Exception as e:
                print(typ, e); ok = False
            check(f"{typ}: added and drawn", ok)
        types = {n["type"] for n in ui_node.load_tree(node, pack).walk()}
        check("all widget types are in the tree", {t for t in pack.widgets if t not in pack.root_types} <= types)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
