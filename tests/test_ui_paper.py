"""Paper preview layout (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_paper as P
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
    a = M.add_widget(t, pack, "label"); b = M.add_widget(t, pack, "button"); c = M.add_widget(t, pack, "entry")
    for i, w in enumerate((a, b, c)):
        t.find(w)["layout"] = {"manager": "grid", "row": i, "column": 0}
    boxes = {x["id"]: x for x in P.Paper(t, pack).boxes(560, 380)}
    check("root fills the paper", (boxes[r]["w"], boxes[r]["h"]) == (560, 380))
    check("grid rows stack down", boxes[a]["y"] < boxes[b]["y"] < boxes[c]["y"] and boxes[a]["x"] == boxes[b]["x"])
    t.set_layout(b, column=1, row=0)
    boxes = {x["id"]: x for x in P.Paper(t, pack).boxes(560, 380)}
    check("grid columns go right", boxes[b]["x"] > boxes[a]["x"] and boxes[b]["y"] == boxes[a]["y"])
    t.set_layout(c, manager="place", x=100, y=200)
    boxes = {x["id"]: x for x in P.Paper(t, pack).boxes(560, 380)}
    check("place uses x/y", (boxes[c]["x"], boxes[c]["y"]) == (100, 200))
    fr = M.add_widget(t, pack, "frame"); inner = M.add_widget(t, pack, "button", selected_id=fr)
    bl = P.Paper(t, pack).boxes(560, 380)
    boxes = {x["id"]: x for x in bl}
    check("children sit inside their frame", boxes[fr]["x"] <= boxes[inner]["x"] and
          boxes[inner]["x"] + boxes[inner]["w"] <= boxes[fr]["x"] + boxes[fr]["w"])
    check("hit test finds the deepest widget, then the window, then nothing",
          P.hit_test(bl, boxes[inner]["x"] + 2, boxes[inner]["y"] + 2) == inner
          and P.hit_test(bl, 559, 379) == r and P.hit_test(bl, 900, 900) is None)
    check("device sizes", P.device_size("phone")[0] < P.device_size("desktop")[0] and P.device_size("nope") == P.device_size("desktop"))
    check("parse font string with braces", P.parse_font("{Segoe UI} 14 bold") == ("Segoe UI", 14, ["bold"]))
    check("parse plain / tuple / none", P.parse_font("Arial 12") == ("Arial", 12, []) and P.parse_font(("Times", 20, "italic")) == ("Times", 20, ["italic"])
          and P.parse_font(None) == (P.DEFAULT_FONT[0], P.DEFAULT_FONT[1], []))
    check("format font round-trips", P.parse_font(P.format_font("Segoe UI", 16, ["italic", "bold"])) == ("Segoe UI", 16, ["bold", "italic"]))
    t3 = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    small = M.add_widget(t3, pack, "label"); big = M.add_widget(t3, pack, "label")
    t3.set_prop(big, "font", "Arial 18")
    bx = {x["id"]: x for x in P.Paper(t3, pack).boxes(560, 380)}
    check("bigger font, bigger box", bx[big]["w"] > bx[small]["w"] and bx[big]["h"] > bx[small]["h"])
    print("\nFAILURES:", FAILURES)

main()
