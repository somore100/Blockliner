"""Reading generated UI code back into a tree (pure, no Tk)."""
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
    pack, _n = ui_pack.load_pack(os.path.join(ROOT, "python", "tkinter"))
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    lab = M.add_widget(t, pack, "label"); btn = M.add_widget(t, pack, "button")
    fr = M.add_widget(t, pack, "frame"); ent = M.add_widget(t, pack, "entry", selected_id=fr)
    t.set_prop(btn, "width", 12); t.find(btn)["layout"] = {"manager": "grid", "row": 0, "column": 1, "padx": 4}
    t.set_event(btn, "command", "h1")
    node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
    names = {"h1": "on_go"}
    ids = {"on_go": "h1"}
    text, _p = ui_node.generate_text(node, pack, names.get)

    tree, probs = ui_parse.read_back(node, pack, text, names.get, ids.get)
    def shape(tr):      # props the code leaves out because they equal the library default (state=normal) are ignored
        return [(n["type"], n["name"], {k: v for k, v in n["props"].items() if k != "state"}, n["layout"], n["events"])
                for n in tr.walk()]
    check("round trip: generated code reads back to the same widgets", tree is not None and shape(tree) == shape(t))
    check("round trip keeps nesting", [c["name"] for c in tree.root["children"]] == [c["name"] for c in t.root["children"]]
          and tree.find(tree.root["children"][2]["id"])["children"][0]["type"] == "entry")

    edited = text.replace("'Button'", "'Save it'").replace("column=1", "column=3")
    tree2, _ = ui_parse.read_back(node, pack, edited, names.get, ids.get)
    b2 = next(n for n in tree2.walk() if n["type"] == "button")
    check("edited values come through", b2["props"]["text"] == "Save it" and b2["layout"]["column"] == 3)

    extra = text.replace("ui = build_UI_1()", "print('hi')\nui = build_UI_1()")
    check("extra code outside the UI is refused, naming it",
          ui_parse.read_back(node, pack, extra, names.get, ids.get)[0] is None
          and "print('hi')" in ui_parse.read_back(node, pack, extra, names.get, ids.get)[1][0])
    inside = text.replace("    return types", "    print('x')\n    return types")
    check("extra code inside the function is refused", ui_parse.read_back(node, pack, inside, names.get, ids.get)[0] is None)
    check("an unknown handler is refused", ui_parse.read_back(node, pack, text.replace("on_go", "gone"), names.get, {}.get)[0] is None)
    check("garbage is refused, not a crash", ui_parse.read_back(node, pack, "x = (", names.get, ids.get)[0] is None
          and ui_parse.read_back(node, pack, "print(1)", names.get, ids.get)[0] is None)
    print("\nFAILURES:", FAILURES)

main()
