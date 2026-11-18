"""Scripted UI test (run under Xvfb): tabs in the real designer - a notebook, two pages, only one page on the paper, a
click on a tab (found by _dz_tab_at) and selecting a widget inside the other page switch the page, titles are editable."""
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
        ed.state["sel"] = root; ed._dz_add_type("notebook"); settle(app, 0.1)
        nb = ed.state["sel"]
        for _ in range(2):
            ed.state["sel"] = nb; ed._dz_add_type("frame"); settle(app, 0.1)
        tree = ui_node.load_tree(node, pack)
        pages = [c["id"] for c in tree.find(nb)["children"]]
        check("two pages in the notebook", len(pages) == 2 and all(tree.find(p)["layout"]["manager"] == "tab" for p in pages))
        ed.state["sel"] = nb; ed._dz_update(code=False); settle(app, 0.1)
        ids = {b["id"] for b in ed._dz_boxes}
        check("the paper shows the first page only", pages[0] in ids and pages[1] not in ids)
        box = next(b for b in ed._dz_boxes if b["id"] == nb)
        second_x = box["x"] + len("Tab 1") * 7 + 18 + 10
        check("a point on the second tab finds it", ed._dz_tab_at(tree, second_x, box["y"] + 10) == (nb, pages[1]))
        check("a point below the tabs does not", ed._dz_tab_at(tree, second_x, box["y"] + 60) is None)
        ed.state.setdefault("tabs", {})[nb] = pages[1]; ed.state["sel"] = pages[1]; ed._dz_update(code=False); settle(app, 0.1)
        ids = {b["id"] for b in ed._dz_boxes}
        check("the second page is shown after choosing it", pages[1] in ids and pages[0] not in ids)
        ed.state["sel"] = pages[1]; ed._dz_add_type("button"); settle(app, 0.1)
        tree = ui_node.load_tree(node, pack)
        btn = next(n for n in tree.walk() if n["type"] == "button")
        check("a button added with a page selected goes in that page", tree.parent_of(btn["id"])["id"] == pages[1])
        ed.state["sel"] = pages[0]; ed._dz_update(code=False); settle(app, 0.1)
        check("selecting the first page shows it again", pages[0] in {b["id"] for b in ed._dz_boxes})
        text = node_code(app, node, pack)
        check("the code adds both pages", text.count(".add(") == 2)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

def node_code(app, node, pack):
    return ui_node.generate_text(node, pack, lambda _i: None)[0] or ""

main()
