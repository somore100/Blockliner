"""Nodes layer with many nodes: only boxes near the view are built; panning builds the ones that come into view,
wires still reach unbuilt boxes, few nodes build everything. Headless (Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nodes_model import make_node, normalize_orders
from ui import BlocklinerUI
import ui_culling

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def build(n):
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = []
    for i in range(n):
        blks = [("assign_variable", {"variable": "a", "value": "1"})]
        if i: blks.append(("func_call", {"name": f"f{i-1}", "args": ""}))
        nd = make_node(f"f{i}", node_id=f"n{i}", blocks=[("func_def", {"name": f"f{i}", "params": "", "_children": blks})])
        nd["canvas_x"], nd["canvas_y"] = 20 + (i % 20) * 320, 40 + (i // 20) * 260
        nodes.append(nd)
    tab["nodes"] = nodes; tab["active_node_id"] = nodes[0]["id"]; tab["file_view_path"] = []
    app.project_blocks = nodes[0]["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update()
    return app, tab

def settle(app):
    for _ in range(3):
        app.update(); app.after(ui_culling.CULL_DELAY_MS + 60); app.update()
    app.cull_update(); app.update()

app, tab = build(10)
check("few nodes: every box is built", len(app._fileview_boxes) == 10 and not app._ghosts())
app.destroy()

app, tab = build(200)
boxes = app._fileview_boxes
check("many nodes: only some boxes are built", 0 < len(boxes) < 80 and len(boxes) + len(app._ghosts()) == 200)
check("the first node (in view) has a box", "n0" in boxes)
check("a far node is a ghost", "n199" in app._ghosts())
wires = app.workspace_canvas.find_withtag("wire")
check("wires are drawn, also to unbuilt boxes", len(wires) >= 190)
check("scroll region reaches the far nodes", float(str(app.workspace_canvas.cget("scrollregion")).split()[3]) > 2000)

# pan to the far end: the near boxes come, the old ones go
c = app.workspace_canvas
z = app.canvas_zoom
c.xview_moveto(0.0)
c.configure(scrollregion=(0, 0, 7000, 3000))
c.xview_moveto(0.5); c.yview_moveto(0.6); settle(app)
check("after panning, the boxes in view exist", any(app._node_hits(n, app._view_rect(0)) and n["id"] in app._fileview_boxes
                                                   for n in tab["nodes"]))
check("after panning, n0 was dropped", "n0" not in app._fileview_boxes and "n0" in app._ghosts())
check("box + ghost always cover every node", len(app._fileview_boxes) + len(app._ghosts()) == 200)
check("no widget leak: far fewer boxes than nodes", len(app._fileview_boxes) < 80)

# editing a node in view keeps working (in place refresh with ghosts around)
vis = next(n["id"] for n in tab["nodes"] if n["id"] in app._fileview_boxes)
check("refresh_nodes_in_place copes with ghosts", app.refresh_nodes_in_place(rebuild_ids=(vis,)) in (True, False))
app.refresh_workspace(); app.update()
check("full refresh builds only the view again", len(app._fileview_boxes) < 80 and len(app._fileview_boxes) + len(app._ghosts()) == 200)
app.destroy()

print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
