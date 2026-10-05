"""Drag-reorder of top-level workspace blocks (whole block is the grab area).
Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI, make_node, normalize_orders
from ui_common import BLOCK_CHUNK
from ui_widgets import BlockWidget

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def assign(i): return ("assign_variable", {"variable": f"v{i}", "value": str(i)})
def names(node): return [p.get("variable", "C") for _b, p in node["blocks"]]

def top(app):
    return sorted([w for w in app.workspace_frame.winfo_children()
                   if isinstance(w, BlockWidget) and w.container_list is app.project_blocks],
                  key=lambda w: w.winfo_rooty())

def open_node(app, tab, node):
    tab["active_node_id"] = node["id"]; app.project_blocks = node["blocks"]
    app.view_mode = "node"; app.refresh_workspace(); app.update(); app.update()
    app.workspace_canvas.yview_moveto(0.0); app.update()

def canvas_bottom(app): return app.workspace_canvas.winfo_rooty() + app.workspace_canvas.winfo_height() - 3
def mid(w): return w.winfo_rooty() + w.winfo_height() // 2
def ev(x, y): return NS(x_root=x, y_root=y)
def cx(w): return w.winfo_rootx() + 30

def drag(app, w, y_to, x_to=None, steps=True):
    """Drive the widget handlers the way Tk would for a press-move-release."""
    x0, y0 = cx(w), w.winfo_rooty() + 8
    w._reorder_press(ev(x0, y0))
    if steps:
        w._reorder_motion(ev(x0, y0 + 2))           # under the threshold
        w._reorder_motion(ev(x_to or x0, y_to))
    w._reorder_release(ev(x_to or x0, y_to)); app.update()

def descendants(w):
    for c in w.winfo_children():
        yield c; yield from descendants(c)

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0"); app.update()
    tab = app.tabs[0]
    node = make_node("n", node_id="n1", blocks=[assign(i) for i in range(5)])
    tab["nodes"] = [node]; tab["file_view_path"] = []; normalize_orders(tab["nodes"])
    def reset(blocks=None):
        node["blocks"][:] = blocks or [assign(i) for i in range(5)]
        open_node(app, tab, node)

    reset(); ws = top(app)
    # ---- binding rules ----
    btns = [d for d in descendants(ws[0]) if isinstance(d, tk.Button)]
    check("buttons are NOT drag-bound (they keep working)", btns and all(not b.bind("<ButtonPress-1>") for b in btns))
    labs = [d for d in descendants(ws[0]) if isinstance(d, tk.Label)]
    check("labels/params area ARE drag-bound (whole block)", labs and all(l.bind("<ButtonPress-1>") for l in labs))
    check("block frame itself is drag-bound", bool(ws[0].bind("<B1-Motion>")))

    # ---- move down / up ----
    drag(app, ws[0], mid(ws[2]) + 5)                     # v0 below the middle of block 2 -> before 3
    check("drag block 0 below block 2 -> v1 v2 v0 v3 v4", names(node) == ["v1", "v2", "v0", "v3", "v4"])
    check("tab marked dirty", tab.get("dirty", True))
    reset(); ws = top(app)
    drag(app, ws[3], ws[1].winfo_rooty() + 2)            # v3 above block 1's middle -> before 1
    check("drag block 3 above block 1 -> v0 v3 v1 v2 v4", names(node) == ["v0", "v3", "v1", "v2", "v4"])
    reset(); ws = top(app)
    drag(app, ws[2], ws[0].winfo_rooty() + 2)
    check("drag to the very top", names(node) == ["v2", "v0", "v1", "v3", "v4"])
    reset(); ws = top(app)
    drag(app, ws[1], canvas_bottom(app))
    check("drag into empty space below -> end", names(node) == ["v0", "v2", "v3", "v4", "v1"])
    reset(); ws = top(app)
    drag(app, ws[4], ws[0].winfo_rooty() + 2)
    check("last block to the top", names(node) == ["v4", "v0", "v1", "v2", "v3"])

    # ---- no-ops ----
    reset(); ws = top(app); before = [id(b) for b in node["blocks"]]
    drag(app, ws[2], mid(ws[2]) - 3)
    check("drop on own upper half = no change", [id(b) for b in node["blocks"]] == before)
    ws = top(app); drag(app, ws[2], mid(ws[2]) + 3)
    check("drop on own lower half = no change", [id(b) for b in node["blocks"]] == before)
    ws = top(app); drag(app, ws[2], mid(ws[3]) - 3)
    check("drop just before the next block = no change", [id(b) for b in node["blocks"]] == before)
    ws = top(app); drag(app, ws[4], canvas_bottom(app))
    check("last block dropped below the end = no change", [id(b) for b in node["blocks"]] == before)
    ws = top(app); drag(app, ws[1], 0, steps=False)      # press+release, no motion = a click
    check("click without motion does nothing", [id(b) for b in node["blocks"]] == before)
    ws = top(app); w = ws[1]; x0, y0 = cx(w), w.winfo_rooty() + 8
    w._reorder_press(ev(x0, y0)); w._reorder_motion(ev(x0 + 3, y0 + 3)); w._reorder_release(ev(x0 + 3, mid(ws[4]))); app.update()
    check("tiny wiggle (under threshold) does nothing", [id(b) for b in node["blocks"]] == before)

    # ---- release outside the workspace cancels ----
    reset(); ws = top(app)
    pal_x = app.winfo_rootx() + 5
    drag(app, ws[0], mid(ws[3]), x_to=pal_x)
    check("release outside the workspace cancels", names(node) == [f"v{i}" for i in range(5)])
    check("indicator removed after cancel", getattr(app, "_drop_line", None) is None)

    # ---- indicator ----
    reset(); ws = top(app); w = ws[0]; x0, y0 = cx(w), w.winfo_rooty() + 8
    w._reorder_press(ev(x0, y0)); w._reorder_motion(ev(x0, mid(ws[3])))
    line = getattr(app, "_drop_line", None)
    check("indicator shown at a real landing spot", line is not None and line.winfo_exists())
    w._reorder_motion(ev(x0, mid(ws[0]) + 3))
    check("indicator hidden over a no-op spot", getattr(app, "_drop_line", None) is None)
    w._reorder_motion(ev(x0, mid(ws[2]) + 5))
    w._reorder_release(ev(x0, mid(ws[2]) + 5)); app.update()
    check("indicator removed on release", getattr(app, "_drop_line", None) is None)
    check("moved on release", names(node) == ["v1", "v2", "v0", "v3", "v4"])

    # ---- move_block_to API edge cases ----
    reset()
    check("bad src -> False", app.move_block_to(9, 0) is False and app.move_block_to(-1, 0) is False)
    check("insert_at beyond end is clamped to end", app.move_block_to(0, 99) and names(node)[-1] == "v0")
    reset(); check("negative insert_at is clamped to the top", app.move_block_to(3, -7) and names(node)[0] == "v3" and len(node["blocks"]) == 5)
    reset(); check("move_block_to(2, 2) is a no-op", app.move_block_to(2, 2) is False)
    check("move_block_to(2, 3) is a no-op", app.move_block_to(2, 3) is False)
    check("move_block_to(2, 4) moves down one", app.move_block_to(2, 4) and names(node) == ["v0", "v1", "v3", "v2", "v4"])
    check("move_block_to(3, 1) moves up two", app.move_block_to(3, 1) and names(node) == ["v0", "v2", "v1", "v3", "v4"])
    check("list identity kept (node['blocks'] is project_blocks)", app.project_blocks is node["blocks"])

    # ---- generated code follows ----
    reset(); app.move_block_to(0, None)
    code = app.generate_code_for_tab(tab, "python")
    check("generated code order follows the move", code.index("v1 = 1") < code.index("v0 = 0"))

    # ---- containers: move with their body; nested blocks are not draggable ----
    cont = ("if_statement", {"condition": "x", "_children": [assign(90), assign(91)]})
    reset([assign(0), cont, assign(1)]); ws = top(app)
    check("3 top-level widgets", len(ws) == 3)
    nested = [d for d in descendants(ws[1]) if isinstance(d, BlockWidget)]
    check("nested blocks exist and are NOT drag-bound", len(nested) == 2 and all(not n.bind("<ButtonPress-1>") for n in nested))
    check("nested block internals not drag-bound", all(not d.bind("<ButtonPress-1>") for n in nested for d in descendants(n)))
    drag(app, ws[1], ws[0].winfo_rooty() + 2)
    check("container moved above block 0", names(node) == ["C", "v0", "v1"])
    check("container keeps its children", [p["variable"] for _b, p in node["blocks"][0][1]["_children"]] == ["v90", "v91"])
    ws = top(app); drag(app, ws[0], canvas_bottom(app))
    check("container moved to the end", names(node) == ["v0", "v1", "C"] and len(node["blocks"][2][1]["_children"]) == 2)

    # ---- collapsed block can be dragged ----
    reset(); node["blocks"][1][1]["_collapsed"] = True; open_node(app, tab, node); ws = top(app)
    drag(app, ws[1], canvas_bottom(app))
    check("collapsed block drags (and stays collapsed)", names(node)[-1] == "v1" and node["blocks"][-1][1].get("_collapsed") is True)

    # ---- lazy window ----
    big = make_node("b", node_id="b1", blocks=[assign(i) for i in range(150)])
    tab["nodes"].append(big); open_node(app, tab, big)
    ws = top(app)
    check("big node windowed", len(ws) == BLOCK_CHUNK)
    drag(app, ws[10], ws[2].winfo_rooty() + 2)
    check("windowed: absolute indexes (v10 now at 2)", big["blocks"][2][1]["variable"] == "v10" and len(big["blocks"]) == 150)
    open_node(app, tab, big); ws = top(app)
    ws = top(app)
    below = app.workspace_frame.winfo_rooty() + ws[-1].winfo_y() + ws[-1].winfo_height() + 50
    check("windowed: below the last rendered block -> append (None)", app.drop_target(below)[0] is None)
    app.move_block_to(1, app.drop_target(below)[0])
    check("windowed: that drop goes to the real end (150th)", big["blocks"][-1][1]["variable"] == "v1")
    check("windowed: no block lost or duplicated", sorted(p["variable"] for _b, p in big["blocks"]) == sorted(f"v{i}" for i in range(150)))
    big["blocks"][:] = [assign(i) for i in range(150)]; open_node(app, tab, big)
    app.move_block_to(0, 140)
    check("move across the window edge reveals the destination", app._win_end >= 140 and big["blocks"][139][1]["variable"] == "v0")
    check("destination widget actually built", any(w.index == 139 for w in top(app)))

    # ---- palette drop + header buttons still work ----
    reset(); ws = top(app)
    [d for d in descendants(ws[0]) if isinstance(d, tk.Button) and d.cget("text") == "\u25bc"][1].invoke(); app.update()
    check("header down-button still works", names(node)[:2] == ["v1", "v0"])

    app.destroy()
    print("\nFAILED:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
