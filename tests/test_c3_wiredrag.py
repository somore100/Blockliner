"""
Phase C3 scripted UI test (run under Xvfb): manual wire-drag.

Not a pytest file - run directly, same convention as test_c2_canvas.py.
Exercises the real ui.py code (BlocklinerUI) by driving the actual
_port_press/_port_motion/_port_release handlers with synthetic event
objects, rather than re-implementing the drag logic in the test. Event
x_root/y_root are computed from the canvas's own screen origin plus a
target canvas-space point, which is the exact inverse of what
_canvas_coords_from_event does - valid as long as the canvas hasn't
been scrolled (true here, fresh render, no scrolling triggered).
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from ui import BlocklinerUI, make_node, find_node_by_id

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def box_center(app, node):
    _, widget = app._fileview_boxes[node["id"]]
    w = widget.winfo_width() or 220
    h = widget.winfo_height() or 70
    return node["canvas_x"] + w / 2, node["canvas_y"] + h / 2


def to_root_event(app, cx, cy):
    """Build a fake event whose x_root/y_root, once run back through
    _canvas_coords_from_event, resolve to canvas point (cx, cy)."""
    root_x = app.workspace_canvas.winfo_rootx() + cx
    root_y = app.workspace_canvas.winfo_rooty() + cy
    return SimpleNamespace(x_root=root_x, y_root=root_y)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()

    tab = app.tabs[app.active_tab_index]
    node_a = tab["nodes"][0]
    node_a["name"] = "main"
    node_b = make_node("helper", node_id="helper1", blocks=[])
    tab["nodes"].append(node_b)

    app.switch_to_file_view()
    app.update()
    app.update_idletasks()

    check("no func_call in node A before drag",
          not any(b[0] == "func_call" for b in node_a["blocks"]))
    check("node A has a wire-drag port (func_call exists for python)",
          "func_call" in app.blocks)

    # --- Drag: press on node A's port, drag over node B, release on it ---
    app._port_press(SimpleNamespace(x_root=0, y_root=0), node_a["id"])
    check("wire-drag state set on press", app._wire_drag_source == node_a["id"])
    check("temp drag line created on press", app._wire_drag_temp_id is not None)

    bcx, bcy = box_center(app, node_b)
    app._port_motion(to_root_event(app, bcx, bcy))
    check("hovering node B sets hover highlight", app._wire_drag_hover_id == node_b["id"])

    app._port_release(to_root_event(app, bcx, bcy))
    check("drag state cleared after release", app._wire_drag_source is None)
    check("temp line removed after release", app._wire_drag_temp_id is None)
    check("hover highlight cleared after release", app._wire_drag_hover_id is None)

    check("func_call block inserted into node A targeting helper",
          any(b[0] == "func_call" and b[1].get("name") == "helper" for b in node_a["blocks"]))

    app.update()
    check("recompute_references resolved main -> helper after drag",
          node_b["id"] in find_node_by_id(tab["nodes"], node_a["id"])["references"])
    check("a wire was drawn for the drag-created reference",
          len(app.workspace_canvas.find_withtag("wire")) > 0)

    # --- Dropping in empty space should not create a second call ---
    calls_before = sum(1 for b in node_a["blocks"] if b[0] == "func_call")
    app._port_press(SimpleNamespace(x_root=0, y_root=0), node_a["id"])
    app._port_release(to_root_event(app, 5000, 5000))  # far off any box
    calls_after = sum(1 for b in node_a["blocks"] if b[0] == "func_call")
    check("dropping in empty space adds no block", calls_before == calls_after)
    check("drag state cleared after empty-space release", app._wire_drag_source is None)

    # --- Dragging onto the source node itself should be a no-op ---
    acx, acy = box_center(app, node_a)
    app._port_press(SimpleNamespace(x_root=0, y_root=0), node_a["id"])
    app._port_release(to_root_event(app, acx, acy))
    calls_after_self = sum(1 for b in node_a["blocks"] if b[0] == "func_call")
    check("dragging onto self adds no block", calls_after == calls_after_self)

    # Screenshot for a visual sanity check
    app.update()
    try:
        import subprocess
        subprocess.run(["import", "-window", "root", "/tmp/c3_wiredrag.png"],
                        check=False, timeout=10)
    except Exception as e:
        print("screenshot skipped:", e)

    # --- Regression: switching to node view and back still works ---
    app.open_node(node_a["id"])
    app.update()
    check("node view still opens cleanly after wire-drag work",
          len(app.workspace_canvas.find_withtag("fileview")) == 0)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("All Phase C3 wire-drag assertions passed.")


if __name__ == "__main__":
    main()
