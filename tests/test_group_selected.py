"""Group selected nodes: Shift+right-click several, then wrap them in one group. Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import groups_model as gm
from nodes_model import make_node, normalize_orders
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)
def labels(menu): return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
def buttons(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, tk.Button): out.append(ch.cget("text"))
        out += buttons(ch)
    return out

def main():
    # ---- pure model
    check("bounds_around empty -> None", gm.bounds_around([]) is None)
    check("bounds_around ignores junk", gm.bounds_around([(0, 0, "x", 5)]) is None)
    b = gm.bounds_around([(100, 100, 50, 40), (300, 200, 60, 30)], pad=10, title=30)
    check("bounds wrap all boxes with pad + title room", b == (90, 60, 280, 180))
    check("one box works", gm.bounds_around([(0, 0, 10, 10)], pad=0, title=0) == (0, 0, 10, 10))

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    ns = [make_node(n, node_id=i, blocks=[]) for n, i in (("alpha", "a1"), ("beta", "b1"), ("gamma", "c1"))]
    a, b_, c = ns
    tab["nodes"] = ns; tab["active_node_id"] = "a1"; tab["file_view_path"] = []
    a["canvas_x"], a["canvas_y"] = 100, 100; b_["canvas_x"], b_["canvas_y"] = 400, 150; c["canvas_x"], c["canvas_y"] = 100, 600
    app.project_blocks = a["blocks"]; normalize_orders(tab["nodes"])
    app.switch_to_file_view(); app.update(); app.update()

    check("nothing selected -> no group", app.group_selected_nodes() is None and not tab.get("groups"))
    app.toggle_node_selected("a1"); app.update()
    check("no button with one selected", not [t for t in buttons(app.node_nav_frame) if "Group 1" in t])
    app.toggle_node_selected("b1"); app.update()
    check("button offered with two selected", "▭ Group 2 selected" in buttons(app.node_nav_frame))
    check("menu offers it on a selected node", "▭ Group 2 selected" in labels(app.build_node_menu("a1")))
    check("menu hides it on an unselected node", not [l for l in labels(app.build_node_menu("c1")) if "Group" in l])

    app.toggle_node_selected("b1"); app.update()
    check("menu hides it with a single selected node", not [l for l in labels(app.build_node_menu("a1")) if "Group" in l])
    app.toggle_node_selected("b1"); app.update()
    g = app.group_selected_nodes(); app.update(); app.update()
    check("group created on the file level", g is not None and tab["groups"] == [g] and g["level"] == "")
    z = app.canvas_zoom
    ok = True
    for n in (a, b_):
        w, h = app._fileview_boxes[n["id"]][1].winfo_reqwidth(), app._fileview_boxes[n["id"]][1].winfo_reqheight()
        ok &= g["x"] <= n["canvas_x"] and g["y"] + 30 <= n["canvas_y"] and \
              n["canvas_x"] + w / z <= g["x"] + g["w"] and n["canvas_y"] + h / z <= g["y"] + g["h"]
    check("group fully wraps both selected boxes (below title bar)", ok)
    check("far node not inside", not gm.contains_center(g, c["canvas_x"], c["canvas_y"], 100, 80))
    check("selection cleared", not app.selected_nodes())
    check("tab marked dirty", tab["dirty"])
    check("group drawn", len(app.workspace_canvas.find_withtag("g_" + g["id"])) == 4)

    # dragging the group moves the grouped nodes, not the far one
    ax, bx, cx = a["canvas_x"], b_["canvas_x"], c["canvas_x"]
    ev = lambda x, y: types.SimpleNamespace(x_root=x, y_root=y, x=x, y=y, widget=None)
    app._group_press(ev(0, 0), g["id"], "move"); app._group_motion(ev(50, 0), g["id"]); app._group_release(ev(50, 0), g["id"])
    check("both grouped nodes moved with the group", a["canvas_x"] == ax + 50 and b_["canvas_x"] == bx + 50)
    check("outside node stayed", c["canvas_x"] == cx)

    # works with a category too, and survives zoom
    app.set_zoom(1.5); app.update()
    app.toggle_node_selected("a1"); app.toggle_node_selected("c1"); app.update()
    exp = gm.bounds_around([(n["canvas_x"], n["canvas_y"], app._fileview_boxes[n["id"]][1].winfo_reqwidth() / 1.5,
                             app._fileview_boxes[n["id"]][1].winfo_reqheight() / 1.5) for n in (a, c)])
    g2 = app.group_selected_nodes(); app.update()
    check("second group has its own id", g2 is not None and g2["id"] != g["id"] and len(tab["groups"]) == 2)
    check("zoomed group is exactly the model-unit bounds (not pixels)", (g2["x"], g2["y"], g2["w"], g2["h"]) == exp)
    app.set_zoom(1.0)

    # not on the Files layer / Blocks layer
    app.goto_layer("files"); app.update()
    app.selected_nodes().update({"a1", "b1"})
    check("refused outside the Nodes layer", app.group_selected_nodes() is None)

    app.destroy()
    print("\nFAILURES:", FAILURES if FAILURES else "none")
    sys.exit(1 if FAILURES else 0)

main()
