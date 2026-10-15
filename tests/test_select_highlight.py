"""Selected file / node / block is outlined in cyan. Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from nodes_model import make_node, normalize_orders
from ui import BlocklinerUI
from ui_canvas import SELECT_COLOR
from ui_widgets import BlockWidget

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def border(w): return str(w.cget("highlightbackground")).lower()
def block_widgets(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, BlockWidget): out.append(ch)
        out += block_widgets(ch)
    return out
def header_of(box):
    for ch in box.winfo_children():
        if ch.bind("<B1-Motion>"): return ch

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    check("selection colour is cyan", SELECT_COLOR.lower() == "#00e5ff")

    tab = app.tabs[0]
    a = make_node("alpha", node_id="a1", blocks=[("print_output", {"value": "'A'"}), ("print_output", {"value": "'B'"})])
    b = make_node("beta", node_id="b1", blocks=[("print_output", {"value": "'C'"})])
    tab["nodes"] = [a, b]; tab["active_node_id"] = "a1"; tab["file_view_path"] = []
    a["canvas_x"], a["canvas_y"] = 20, 20; b["canvas_x"], b["canvas_y"] = 300, 20
    app.project_blocks = a["blocks"]; normalize_orders(tab["nodes"])

    # ---- node
    app.switch_to_file_view(); app.update(); app.update()
    shift = types.SimpleNamespace(state=1, x_root=0, y_root=0, widget=None)
    app._on_node_box_right_click(shift, "a1")
    check("selected node is cyan", border(app._fileview_boxes["a1"][1]) == SELECT_COLOR)
    check("other node is not", border(app._fileview_boxes["b1"][1]) != SELECT_COLOR)

    # ---- file (Files layer)
    app.switch_to_files_view() if hasattr(app, "switch_to_files_view") else app._show_active_file("files")
    app.update(); app.update()
    box = app._filesview_boxes[0][1]
    check("file box starts unselected", border(box) != SELECT_COLOR)
    press = types.SimpleNamespace(x_root=0, y_root=0, x=0, y=0, widget=None)
    header_of(box).event_generate("<ButtonPress-1>", x=3, y=3)
    app.update()
    check("clicking a file selects it (cyan)", border(app._filesview_boxes[0][1]) == SELECT_COLOR)
    app.render_files_view(); app.update()
    check("file stays selected after redraw", border(app._filesview_boxes[0][1]) == SELECT_COLOR)

    # ---- block
    app.open_node("a1") if hasattr(app, "open_node") else None
    app.refresh_workspace(); app.update(); app.update()
    ws = block_widgets(app.workspace_frame)
    top = [w for w in ws if w.container_list is app.project_blocks]
    check("two top-level blocks shown", len(top) >= 2)
    check("no block selected at first", all(border(w) != SELECT_COLOR for w in top))
    app.select_block(1, app.project_blocks); app.update()
    top = [w for w in block_widgets(app.workspace_frame) if w.container_list is app.project_blocks]
    sel = [w for w in top if w.index == 1][0]; other = [w for w in top if w.index == 0][0]
    check("selected block is cyan", border(sel) == SELECT_COLOR)
    check("other block is not", border(other) != SELECT_COLOR)
    sel.on_hover(None); sel.on_leave(None)
    check("stays cyan after hover/leave", border(sel) == SELECT_COLOR)
    app.select_block(0, app.project_blocks); app.update()
    top = [w for w in block_widgets(app.workspace_frame) if w.container_list is app.project_blocks]
    check("selecting another moves the highlight",
          border([w for w in top if w.index == 0][0]) == SELECT_COLOR
          and border([w for w in top if w.index == 1][0]) != SELECT_COLOR)
    app.refresh_workspace(); app.update()
    top = [w for w in block_widgets(app.workspace_frame) if w.container_list is app.project_blocks]
    check("block selection survives redraw", border([w for w in top if w.index == 0][0]) == SELECT_COLOR)
    # a different node's block list must not show a stale highlight
    app.project_blocks = b["blocks"]; app.refresh_workspace(); app.update()
    top = [w for w in block_widgets(app.workspace_frame) if w.container_list is app.project_blocks]
    check("other node's block is not highlighted", all(border(w) != SELECT_COLOR for w in top))

    app.destroy()
    print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
    sys.exit(1 if FAILURES else 0)

main()
