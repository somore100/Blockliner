"""Dragging / resizing widgets on the designer paper (pure, no Tk)."""
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

def grid_widget(t, pack, wtype, row):
    w = M.add_widget(t, pack, wtype)
    t.find(w)["layout"] = {"manager": "grid", "row": row, "column": 0}
    return w

def layout(t, pack):
    paper = P.Paper(t, pack)
    boxes = paper.boxes(560, 380)
    return paper, boxes, {b["id"]: b for b in boxes}

def main():
    pack, _n = ui_pack.load_pack(os.path.join(ROOT, "python", "tkinter"))
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    r = t.root["id"]
    check("new widgets are placed freely", M.resize_edges(t, pack, M.add_widget(t, pack, "label")) == "nsew")
    t.remove(t.root["children"][0]["id"])
    a, b, e = grid_widget(t, pack, "label", 0), grid_widget(t, pack, "button", 1), grid_widget(t, pack, "entry", 2)
    check("root can't move or resize", not M.can_move(t, r) and M.resize_edges(t, pack, r) == "")
    check("grid entry resizes east only", M.resize_edges(t, pack, e) == "e")
    check("grid checkbutton (no width) can't resize", M.resize_edges(t, pack, grid_widget(t, pack, "checkbutton", 3)) == "")
    check("grid text resizes both ways", "s" in M.resize_edges(t, pack, grid_widget(t, pack, "text", 4)))

    paper, boxes, by = layout(t, pack)
    bb = by[b]
    # drag the button onto the label's cell -> they swap
    ch = M.move_changes(t, paper, boxes, b, by[a]["x"], by[a]["y"], bb["w"], bb["h"])
    check("grid drop on a taken cell swaps", ch[b]["layout"] == {"row": 0, "column": 0} and ch[a]["layout"] == {"row": 1, "column": 0})
    # drag far right -> new column
    ch = M.move_changes(t, paper, boxes, b, 500, by[a]["y"], bb["w"], bb["h"])
    check("grid drop right of everything makes a new column", ch[b]["layout"]["column"] == 1 and len(ch) == 1)
    check("grid drop on its own cell changes nothing", M.move_changes(t, paper, boxes, b, bb["x"], bb["y"], bb["w"], bb["h"]) == {})
    before = len(t._undo)
    t.edit_many(M.move_changes(t, paper, boxes, b, by[a]["x"], by[a]["y"], bb["w"], bb["h"]))
    check("swap is one undo step", len(t._undo) == before + 1 and t.find(a)["layout"]["row"] == 1)
    t.undo()
    check("undo puts both back", t.find(a)["layout"]["row"] == 0 and t.find(b)["layout"]["row"] == 1)

    # resize grid entry -> width chars
    paper, boxes, by = layout(t, pack)
    eb = by[e]
    ch = M.resize_changes(t, pack, boxes, e, eb["x"], eb["y"], 7 * 30 + 10, eb["h"])
    check("grid resize sets the width setting", ch == {e: {"props": {"width": 30}}})

    # place widget: move + resize, all edges
    t.set_layout(e, manager="place", x=100, y=200)
    paper, boxes, by = layout(t, pack)
    eb = by[e]
    check("place resizes on every edge", M.resize_edges(t, pack, e) == "nsew")
    ch = M.move_changes(t, paper, boxes, e, 150, 50, eb["w"], eb["h"])
    check("place drag sets x/y", ch == {e: {"layout": {"x": 150, "y": 50}}})
    check("place can't go left of its parent", M.move_changes(t, paper, boxes, e, -40, 10, 5, 5)[e]["layout"]["x"] == 0)
    x, y, w, h = M.resize_box(eb, "nw", 10, 5)
    check("pulling the top-left corner moves and shrinks", (x, y, w, h) == (eb["x"] + 10, eb["y"] + 5, eb["w"] - 10, eb["h"] - 5))
    check("resize stops at the minimum size", M.resize_box(eb, "e", -1000, 0)[2] == M.MIN_SIZE)
    ch = M.resize_changes(t, pack, boxes, e, x, y, w, h)
    check("place resize writes x, y, width, height", ch[e]["layout"] == {"x": 110, "y": 205, "width": eb["w"] - 10, "height": eb["h"] - 5})

    # handles
    check("handle: corner", M.handle_at(eb, "nsew", eb["x"] + eb["w"], eb["y"] + eb["h"]) == "se")
    check("handle: middle is none", M.handle_at(eb, "nsew", eb["x"] + eb["w"] / 2, eb["y"] + eb["h"] / 2) == "")
    check("handle: only allowed edges", M.handle_at(eb, "e", eb["x"], eb["y"]) == "")

    # into and out of a frame (place widgets)
    t2 = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    fr = M.add_widget(t2, pack, "frame"); t2.set_layout(fr, x=200, y=100)
    btn = M.add_widget(t2, pack, "button")
    paper, boxes, by = layout(t2, pack)
    fb, bb = by[fr], by[btn]
    ch = M.move_changes(t2, paper, boxes, btn, fb["x"] + 20, fb["y"] + 10, bb["w"] - 60, bb["h"] - 20, pack=pack)
    check("drop inside a frame moves the widget into it", ch[btn]["parent"] == fr and ch[btn]["layout"]["x"] == 20)
    before = len(t2._undo)
    t2.edit_many(ch)
    check("move into frame is one undo step", t2.parent_of(btn)["id"] == fr and len(t2._undo) == before + 1)
    paper, boxes, by = layout(t2, pack)
    ch = M.move_changes(t2, paper, boxes, btn, 5, 5, 20, 20, pack=pack)
    check("drop outside the frame moves it back to the window", ch[btn]["parent"] == t2.root["id"])
    check("a frame can't be dropped into itself", M.drop_container(t2, pack, boxes, fr, by[fr]["x"] + 5, by[fr]["y"] + 5) == t2.root["id"])
    t2.undo()
    check("undo takes it out again", t2.parent_of(btn)["id"] == t2.root["id"])
    print("\nFAILURES:", FAILURES)

main()
