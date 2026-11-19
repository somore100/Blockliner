"""Scripted UI test (run under Xvfb): a menu bar in the real designer - a menu is added (making the bar), the strip is
drawn, clicking a title selects that menu, and the Layout settings are hidden for a menu item."""
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
        app.open_node(node["id"]); settle(app)
        ed = app.designer_editor
        root = ui_node.load_tree(node, pack).root["id"]
        ed.state["sel"] = root; ed._dz_add_type("menu"); settle(app, 0.1)
        menu = ed.state["sel"]
        ed._dz_add_type("menuitem"); settle(app, 0.1)
        item = ed.state["sel"]
        tree = ui_node.load_tree(node, pack)
        check("bar, menu and item", [tree.find(i)["type"] for i in (tree.parent_of(menu)["id"], menu, item)] == ["menubar", "menu", "menuitem"])
        check("the strip is drawn", len(ed._dz_canvas.find_withtag("all")) > 0 and ed._dz_menu_bar(tree) is not None)
        check("no menu box is on the paper", not {b["type"] for b in ed._dz_boxes} & {"menu", "menuitem", "menubar"})
        titles = ed._dz_menu_titles(tree, ed._dz_menu_bar(tree))
        m, x, w = titles[0]
        check("a click on the title finds the menu", ed._dz_menu_at(tree, x + 2, 30) == menu)
        check("a click elsewhere on the strip finds the bar", ed._dz_menu_at(tree, x + w + 50, 30) == tree.parent_of(menu)["id"])
        check("nothing off the strip", ed._dz_menu_at(tree, x + 2, 100) is None)
        ed.state["sel"] = item; ed._dz_update(code=False); settle(app, 0.1)
        from tkinter import Label
        labels = []
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, Label): labels.append(str(c.cget("text")))
                walk(c)
        walk(ed._dz_props_frame)
        check("a menu item has no Layout section", "Layout" not in labels and "LAYOUT" not in [l.upper() for l in labels if l.upper() == "LAYOUT"])
        ed.state["sel"] = menu; ed._dz_update(code=False); settle(app, 0.1)
        labels.clear(); walk(ed._dz_props_frame)
        check("a menu has its Placement (title)", any("Menu title" in l or "Placement" in l for l in labels))
        text = node_code(app, node, pack)
        check("the code builds the menu", "add_cascade" in text and "add_command" in text)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

def node_code(app, node, pack):
    return ui_node.generate_text(node, pack, lambda _i: None)[0] or ""

main()
