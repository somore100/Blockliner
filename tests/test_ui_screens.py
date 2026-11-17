"""Screens and show/hide in a UI (run under Xvfb): the tree marks screens, the code has show_widget / hide_widget /
show_screen, it reads back, and it really shows and hides widgets in tkinter (place and grid)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_parse, ui_pack
import ui_designer_model as M
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def build(lib="tkinter"):
    pack, _ = ui_pack.load_pack(os.path.join(ROOT, "python", lib))
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    return pack, t

def main():
    pack, t = build()
    a = M.add_widget(t, pack, "frame"); b = M.add_widget(t, pack, "frame")
    btn = M.add_widget(t, pack, "button", selected_id=a)
    lbl = M.add_widget(t, pack, "label", selected_id=b)
    check("no screens at first", t.screens() == [])
    t.set_screen(a); t.set_screen(b)
    check("two screens, in order", t.screens() == ["frame", "frame_2"])
    try:
        t.set_screen(btn); ok = False
    except ValueError:
        ok = True
    check("a button inside a frame can't be a screen", ok)
    t.set_screen(b, False)
    check("a screen can be unmarked", t.screens() == ["frame"])
    t.set_screen(b)
    check("screens survive undo/redo", t.undo() and t.screens() == ["frame"] and t.redo() and t.screens() == ["frame", "frame_2"])
    check("the flag is saved and loaded", UITree.from_dict(t.to_dict(), is_container=pack.is_container).screens() == ["frame", "frame_2"])

    node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
    text, _p = ui_node.generate_text(node, pack, lambda _i: None)
    check("the code has the helpers and the screen list", "def show_screen" in text and "screens = ['frame', 'frame_2']" in text and "show_screen('frame')" in text)
    tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
    check(f"it reads back with its screens {probs}", tree is not None and tree.screens() == ["frame", "frame_2"])
    # a UI without screens still gets show/hide
    pack2, t2 = build()
    M.add_widget(t2, pack2, "button")
    text2, _ = ui_node.generate_text(ui_node.make_ui_node("U", "u2", t2, order=1), pack2, lambda _i: None)
    check("without screens: show/hide only, nothing is hidden at start", "def hide_widget" in text2 and "screens = []" in text2 and "show_screen('" not in text2)

    # it really works in tkinter
    import tkinter as tk
    ns = {}
    code = text.replace("ui.root.mainloop()", "")
    exec(compile(code, "<ui>", "exec"), ns)
    ui = ns["ui"]
    ui.root.update()
    check("first screen shows, the other is hidden", ui.frame.winfo_manager() == "place" and ui.frame_2.winfo_manager() == "")
    ui.show_screen("frame_2"); ui.root.update()
    check("show_screen switches", ui.frame.winfo_manager() == "" and ui.frame_2.winfo_manager() == "place")
    ui.show_screen("frame"); ui.root.update()
    check("and back, the button inside is still placed", ui.frame.winfo_manager() == "place" and ui.button.winfo_manager() == "place")
    ui.hide_widget("button"); ui.root.update()
    check("hide_widget hides", ui.button.winfo_manager() == "")
    ui.hide_widget("button"); ui.show_widget("button"); ui.root.update()
    check("hiding twice then showing once brings it back", ui.button.winfo_manager() == "place")
    ui.show_widget("button")
    check("showing a visible widget does nothing", ui.button.winfo_manager() == "place")
    ui.root.destroy()
    # grid
    pack3, t3 = build()
    g = M.add_widget(t3, pack3, "label")
    t3.find(g)["layout"] = {"manager": "grid", "row": 1, "column": 2}
    text3, _ = ui_node.generate_text(ui_node.make_ui_node("U", "u3", t3, order=1), pack3, lambda _i: None)
    ns3 = {}
    exec(compile(text3.replace("ui.root.mainloop()", ""), "<ui>", "exec"), ns3)
    u3 = ns3["ui"]; u3.root.update()
    u3.hide_widget("label"); u3.root.update()
    hidden = u3.label.winfo_manager() == ""
    u3.show_widget("label"); u3.root.update()
    check("grid: hide and show", hidden and u3.label.winfo_manager() == "grid" and u3.label.grid_info()["row"] == 1 and u3.label.grid_info()["column"] == 2)
    u3.root.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
