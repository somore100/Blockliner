"""UI designer helpers (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
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
    r = t.root["id"]
    check("nothing selected: goes under the root", M.add_target(t, pack, None) == r)
    b1 = M.add_widget(t, pack, "button")
    check("add gives defaults, a free place spot and a design size", t.find(b1)["props"] == {"text": "Button", "state": "normal"}
          and t.find(b1)["layout"] == {"manager": "place", "x": 10, "y": 10} and t.find(b1)["design"] == {"w": 100, "h": 32})
    b2 = M.add_widget(t, pack, "label", selected_id=b1)
    check("selected leaf: the new widget becomes its sibling, next row", t.parent_of(b2)["id"] == r and t.find(b2)["layout"]["y"] == 44)
    fr = M.add_widget(t, pack, "frame")
    inner = M.add_widget(t, pack, "entry", selected_id=fr)
    check("selected container: the new widget goes inside it", t.parent_of(inner)["id"] == fr and t.find(inner)["layout"]["y"] == 10)
    check("root types and unknown types can't be added", M.add_widget(t, pack, "window") is None and M.add_widget(t, pack, "nope") is None)
    check("unknown selected id falls back to the root", M.add_target(t, pack, "gone") == r)

    check("move_sibling down and up", M.move_sibling(t, b1, 1) and [c["id"] for c in t.root["children"]][:2] == [b2, b1]
          and M.move_sibling(t, b1, -1) and t.root["children"][0]["id"] == b1)
    check("move_sibling stops at the ends and ignores the root", not M.move_sibling(t, b1, -1) and not M.move_sibling(t, r, 1)
          and not M.move_sibling(t, fr, 1))

    check("coerce: ints", M.coerce_value("int", " 12 ") == (True, 12) and M.coerce_value("int", "x") == (False, None))
    check("coerce: floats and empty", M.coerce_value("float", "1.5") == (True, 1.5) and M.coerce_value("string", "  ") == (True, None))
    check("coerce: bool and list", M.coerce_value("bool", "Yes") == (True, True) and M.coerce_value("bool", "no") == (True, False)
          and M.coerce_value("list", "a, b,, c") == (True, ["a", "b", "c"]))
    check("coerce: text kinds keep the text", M.coerce_value("string", " hi there ") == (True, "hi there") and M.coerce_value("code", "x+1") == (True, "x+1"))
    check("show_value", M.show_value("list", ["a", "b"]) == "a, b" and M.show_value("int", None) == "" and M.show_value("string", "x") == "x")
    rows = M.outline_rows(t)
    check("outline: depth-first with depths", rows[0][3] == 0 and rows[0][1] == "" and all(x[3] >= 1 for x in rows[1:])
          and [x[0] for x in rows].index(inner) == [x[0] for x in rows].index(fr) + 1 and [x[3] for x in rows if x[0] == inner] == [2])

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
