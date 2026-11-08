"""Pure test: pulling selected blocks out of a node into a new node (block_split.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import block_split as bs
from nodes_model import make_node, sorted_function_nodes

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def blocks(*names):
    return [("print_output", {"value": n}) for n in names]


def names(bl):
    return [p["value"] for _b, p in bl]


kept, taken, tail = bs.split_blocks(blocks("a", "b", "c", "d", "e"), {1, 2})
check("selected blocks are taken in order", names(taken) == ["b", "c"])
check("blocks before stay", names(kept) == ["a"])
check("blocks after the last selected become the tail", names(tail) == ["d", "e"])

kept, taken, tail = bs.split_blocks(blocks("a", "b", "c", "d", "e"), {0, 3})
check("a gap between selected blocks stays in the node", names(kept) == ["b", "c"] and names(taken) == ["a", "d"])
check("the tail is what follows the last selected", names(tail) == ["e"])

kept, taken, tail = bs.split_blocks(blocks("a", "b", "c"), {1, 2})
check("selecting the end leaves no tail", tail == [] and names(kept) == ["a"])
check("nothing selected takes nothing", bs.split_blocks(blocks("a"), set())[1] == [])
check("indices out of range are ignored", bs.split_blocks(blocks("a", "b"), {5, 1})[1] == blocks("b"))

# placing the new nodes keeps the run order
a = make_node("A", node_id="a", order=1)
b = make_node("B", node_id="b", order=2)
c = make_node("C", node_id="c", order=3)
a["canvas_x"], a["canvas_y"] = 100, 100
nodes = [a, b, c]
n1, n2 = make_node("A part", node_id="n1"), make_node("A rest", node_id="n2")
bs.place_after(nodes, a, [n1, n2])
check("new nodes follow the original in the list", [n["id"] for n in nodes] == ["a", "n1", "n2", "b", "c"])
check("they run right after the original", [n["id"] for n in sorted_function_nodes(nodes)] == ["a", "n1", "n2", "b", "c"])
check("later nodes were pushed back", b["order"] == 4 and c["order"] == 5)
check("they sit next to the original on the canvas", n1["canvas_x"] == 140 and n2["canvas_y"] == 220)

# a node inside a class
inner = make_node("inner", node_id="i", order=1)
cls = make_node("K", node_id="k", kind="class", child_nodes=[inner])
other = make_node("O", node_id="o", order=2)
tree = [cls, other]
x = make_node("x", node_id="x")
bs.place_after(tree, inner, [x])
check("placed inside the same class", [n["id"] for n in cls["child_nodes"]] == ["i", "x"] and len(tree) == 2)
check("run order across the class holds", [n["id"] for n in sorted_function_nodes(tree)] == ["i", "x", "o"])

# an unassigned (not running) node: the pieces don't start running
u = make_node("U", node_id="u")
u["order"] = None                                  # explicitly unassigned
y = make_node("y", node_id="y")
bs.place_after([u], u, [y])
check("pieces of an unassigned node stay unassigned", y["order"] is None)

# a node with no order key at all (old data) is numbered first
legacy = [make_node("L1", node_id="l1"), make_node("L2", node_id="l2")]
z = make_node("z", node_id="z")
bs.place_after(legacy, legacy[0], [z])
check("legacy nodes get numbered, new node goes second", [n["id"] for n in sorted_function_nodes(legacy)] == ["l1", "z", "l2"])
try:
    bs.place_after([a], make_node("q", node_id="q"), [x])
    raised = False
except ValueError:
    raised = True
check("a node that is not in the file raises", raised)

# clicks: the default mode, Shift+click first and last
c = bs.click
check("plain click picks only that block", c({1, 2}, 4, 1, False, False) == ({4}, 4))
sel, pend = c({1}, 3, 1, False, True)                      # plain click on 1, then shift+click 3
check("shift+click after a plain click picks the range", sel == {1, 2, 3} and pend is None)
sel, pend = c(set(), 2, None, False, True)
check("a first shift+click picks that block and waits for the end", sel == {2} and pend == 2)
sel, pend = c(sel, 5, pend, False, True)
check("the second shift+click picks everything between", sel == {2, 3, 4, 5} and pend is None)
sel, pend = c(sel, 8, pend, False, True)
sel, pend = c(sel, 10, pend, False, True)
check("a second section adds to the first", sel == {2, 3, 4, 5, 8, 9, 10})
sel, pend = c(sel, 4, pend, False, True)
check("shift+click on a picked block drops it", sel == {2, 3, 5, 8, 9, 10} and pend is None)
sel, pend = c({4}, 2, 4, False, True)
check("a range works upward too", sel == {2, 3, 4} | {4})
check("ctrl+click adds one block", c({1}, 3, 1, True, False) == ({1, 3}, None))
check("ctrl+click again removes it", c({1, 3}, 3, None, True, False) == ({1}, None))

# single-click mode: every click toggles
check("single mode: a click picks", c(set(), 3, None, False, False, "single") == ({3}, None))
check("single mode: clicks add up", c({3}, 6, None, False, False, "single") == ({3, 6}, None))
check("single mode: a click on a picked block drops it", c({3, 6}, 3, None, False, False, "single") == ({6}, None))

# first-and-last mode: no modifier keys
sel, pend = c(set(), 1, None, False, False, "range")
check("range mode: the first click picks one block", sel == {1} and pend == 1)
sel, pend = c(sel, 6, pend, False, False, "range")
check("range mode: the second click picks everything between", sel == {1, 2, 3, 4, 5, 6} and pend is None)
sel, pend = c(sel, 9, pend, False, False, "range")
check("range mode: a third click starts over", sel == {9} and pend == 9)
check("range mode: clicking the first block again lets go", c({4}, 4, 4, False, False, "range") == (set(), None))
check("range mode: ctrl+click still toggles one", c({1, 2}, 5, None, True, False, "range") == ({1, 2, 5}, None))
check("unknown mode names fall back to shift", bs.normalize_select_mode("zzz") == "shift" and bs.normalize_select_mode("range") == "range")

print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
