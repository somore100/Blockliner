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
        tree = ui_node.load_tree(node, pack)
        ed._dz_add_screen(); settle(app, 0.1); ed._dz_add_screen(); settle(app, 0.1)
        tree = ui_node.load_tree(node, pack)
        check("+ Screen adds two screens", tree.screens() == ["screen_1", "screen_2"])
        check("they fill the window", all(c["layout"].get("width") for c in tree.root["children"] if c.get("screen")))
        ed._dz_set_screen_view("screen_1"); settle(app, 0.1)
        ids = {b["id"] for b in ed._dz_boxes}
        s2 = next(c for c in tree.root["children"] if c["name"] == "screen_2")
        check("designing one screen leaves the other off the paper", s2["id"] not in ids)
        ed._dz_set_screen_view("All"); settle(app, 0.1)
        check("All shows both", s2["id"] in {b["id"] for b in ed._dz_boxes})
        ed._dz_set_screen(s2["id"], False); settle(app, 0.1)
        check("unmarking a screen", ui_node.load_tree(node, pack).screens() == ["screen_1"])
        check("screen names are offered to blocks", ui_node.screen_names(node) == ["screen_1"])
        check("all widget types are in the tree", {t for t in pack.widgets if t not in pack.root_types} <= types)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
