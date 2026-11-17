"""Every widget of the shipped UI libraries can be added, generates code that compiles, and reads back the same."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_parse
import ui_designer_model as M
import ui_pack
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    for lib in ("tkinter", "customtkinter"):
        pack, notes = ui_pack.load_pack(os.path.join(ROOT, "python", lib))
        check(f"{lib}: loads with no notes {notes}", pack is not None and not notes)
        t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
        containers = []
        for typ in pack.widgets:
            if typ in pack.root_types:
                continue
            wid = M.add_widget(t, pack, typ)
            if pack.is_container(typ):
                containers.append(wid)
        for c in containers:                              # a widget inside every new container
            M.add_widget(t, pack, "label", selected_id=c)
        node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
        text, _p = ui_node.generate_text(node, pack, lambda _i: None)
        try:
            compile(text, "<ui>", "exec")
            ok = True
        except SyntaxError as e:
            ok = False
            print(e)
        check(f"{lib}: the generated code compiles", ok)
        tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
        check(f"{lib}: it reads back ({probs})", tree is not None and [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()])
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
