"""Palette drop inserts at the drop position (absolute index, lazy window
safe) instead of appending; click-add still appends; indicator line follows
the drag. Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
from tkinter import ttk
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import BlocklinerUI, make_node, normalize_orders
from ui_common import BLOCK_CHUNK
from ui_widgets import BlockWidget, PaletteBlockItem

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def assign(i): return ("assign_variable", {"variable": f"v{i}", "value": str(i)})

def top_widgets(app):
    return sorted([w for w in app.workspace_frame.winfo_children()
                   if isinstance(w, BlockWidget) and w.container_list is app.project_blocks], key=lambda w: w.winfo_rooty())

def find_buttons(root, text):
    out = []
    for w in root.winfo_children():
        if isinstance(w, (tk.Button, ttk.Button)) and str(w.cget("text")).startswith(text): out.append(w)
        out += find_buttons(w, text)
    return out

def open_node(app, tab, node):
    tab["active_node_id"] = node["id"]; app.project_blocks = node["blocks"]
    app.view_mode = "node"; app.refresh_workspace(); app.update(); app.update()
    app.workspace_canvas.yview_moveto(0.0); app.update()

def all_descendants(w):
    for c in w.winfo_children():
        yield c; yield from all_descendants(c)

def mid(w): return w.master.winfo_rooty() + w.winfo_y() + w.winfo_height() // 2

def confirm_dialog(app):
    dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    find_buttons(dlg, "Save & Add")[0].invoke(); app.update()

def names(node): return [p["variable"] for _b, p in node["blocks"]]

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0"); app.update()
    ui.messagebox.askyesno = lambda *a, **k: True
    tab = app.tabs[0]
    node = make_node("n", node_id="n1", blocks=[assign(i) for i in range(5)])
    tab["nodes"] = [node]; tab["file_view_path"] = []; normalize_orders(tab["nodes"])
    open_node(app, tab, node)
    mod = app.blocks["assign_variable"]
    ws = top_widgets(app)
    check("5 top-level widgets rendered", len(ws) == 5)

    # ---- drop_target geometry ----
    check("above first block's middle -> index 0", app.drop_target(ws[0].winfo_rooty() + 1)[0] == 0)
    check("between block 1 and 2 -> index 2", app.drop_target((mid(ws[1]) + mid(ws[2])) // 2)[0] == 2)
    check("just above block 3's middle -> index 3", app.drop_target(mid(ws[3]) - 2)[0] == 3)
    check("just below block 3's middle -> index 4", app.drop_target(mid(ws[3]) + 2)[0] == 4)
    check("below the last block -> append (None)", app.drop_target(mid(ws[4]) + 200)[0] is None)
    ly = app.drop_target((mid(ws[1]) + mid(ws[2])) // 2)[1]
    check("indicator y sits just above the target block", abs(ly - (ws[2].winfo_y() - 4)) <= 1)

    # ---- full flow: drop between 1 and 2 ----
    app.add_block_from_drop(mod, 0, (mid(ws[1]) + mid(ws[2])) // 2)
    app.update()
    dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    entries = [w for w in dlg.winfo_children()]
    app.edit_block_params  # keep reference (no-op)
    confirm_dialog(app)
    check("block with default params inserted at index 2", len(node["blocks"]) == 6 and node["blocks"][2][0] == "assign_variable")

    # use explicit params so we can tell blocks apart
    def drop_named(name, y):
        real = app.edit_block_params
        def patched(m, params, add_mode=True, index=None, container_list=None, insert_at=None):
            return real(m, {"variable": name, "value": "1"}, add_mode=add_mode, index=index,
                        container_list=container_list, insert_at=insert_at)
        app.edit_block_params = patched
        try:
            app.add_block_from_drop(mod, 0, y); app.update()
            confirm_dialog(app)
        finally:
            app.edit_block_params = real

    open_node(app, tab, node); node["blocks"][:] = [assign(i) for i in range(5)]; open_node(app, tab, node)
    ws = top_widgets(app)
    drop_named("X", (mid(ws[1]) + mid(ws[2])) // 2)
    check("drop between 1 and 2: v0 v1 X v2 v3 v4", names(node) == ["v0", "v1", "X", "v2", "v3", "v4"])
    check("generated code order follows", app.generate_code_for_tab(tab, "python").index("X = 1") < app.generate_code_for_tab(tab, "python").index("v2 = 2"))
    open_node(app, tab, node); ws = top_widgets(app)
    drop_named("TOP", ws[0].winfo_rooty() + 1)
    check("drop at the very top inserts first", names(node)[0] == "TOP" and len(node["blocks"]) == 7)
    open_node(app, tab, node); ws = top_widgets(app)
    drop_named("END", mid(ws[-1]) + 300)
    check("drop in empty space below appends", names(node)[-1] == "END" and len(node["blocks"]) == 8)

    # click-add (no position) still appends
    real = app.edit_block_params
    app.edit_block_params = lambda m, params, **kw: real(m, {"variable": "CLICK", "value": "1"}, **kw)
    app.add_block_to_workspace(mod); app.update(); confirm_dialog(app)
    app.edit_block_params = real
    check("click-add still appends at the end", names(node)[-1] == "CLICK")

    # a drop into a small node shows the new block immediately
    open_node(app, tab, node); before = len(top_widgets(app)); total = len(node["blocks"])
    ws = top_widgets(app); drop_named("VIS", (mid(ws[1]) + mid(ws[2])) // 2)
    check("small node: inserted block is built (widget count grows)", len(top_widgets(app)) == before + 1 and len(node["blocks"]) == total + 1)
    check("small node: the new block is the widget at its index", any(w.index == 2 and w.params.get("variable") == "VIS" for w in top_widgets(app)))

    # ---- empty workspace ----
    empty = make_node("e", node_id="e1", blocks=[])
    tab["nodes"].append(empty); open_node(app, tab, empty)
    check("empty workspace -> append", app.drop_target(500)[0] is None)
    drop_named("FIRST", 500)
    check("drop on an empty workspace adds the block", names(empty) == ["FIRST"])

    # ---- nested container children are ignored, top level used ----
    cont = ("if_statement", {"condition": "x", "_children": [assign(90), assign(91)]})
    nest = make_node("c", node_id="c1", blocks=[assign(0), cont, assign(1)])
    tab["nodes"].append(nest); open_node(app, tab, nest)
    ws = top_widgets(app)
    check("only top-level widgets are drop targets (3)", len(ws) == 3)
    inner_y = ws[1].winfo_rooty() + ws[1].winfo_height() - 10  # inside the container body, lower half
    check("drop inside a container's lower half -> after it, top level", app.drop_target(inner_y)[0] == 2)
    check("drop in a container's upper half -> before it", app.drop_target(ws[1].winfo_rooty() + 3)[0] == 1)
    drop_named("AFTERIF", inner_y)
    check("container children untouched", len(nest["blocks"][1][1]["_children"]) == 2 and names(nest)[2] if False else len(nest["blocks"][1][1]["_children"]) == 2)
    check("block landed at top level after the container", nest["blocks"][2][1].get("variable") == "AFTERIF")

    # ---- lazy window: absolute indexes ----
    big = make_node("b", node_id="b1", blocks=[assign(i) for i in range(150)])
    tab["nodes"].append(big); open_node(app, tab, big)
    ws = top_widgets(app)
    check("big node windowed", len(ws) == BLOCK_CHUNK)
    check("below last rendered block (window not at end) -> append to the real end", app.drop_target(mid(ws[-1]) + 500)[0] is None)
    drop_named("WIN", (mid(ws[9]) + mid(ws[10])) // 2)
    check("drop inside window uses the absolute index (10)", big["blocks"][10][1]["variable"] == "WIN" and len(big["blocks"]) == 151)
    check("inserted block is visible after refresh", any(w.index == 10 for w in top_widgets(app)))
    # scrolled-down window: start > 0
    big2 = make_node("b2", node_id="b2", blocks=[assign(i) for i in range(150)])
    tab["nodes"].append(big2); open_node(app, tab, big2)
    app._show_more_blocks(); app.update(); app.workspace_canvas.yview_moveto(1.0); app.update()
    app._win_start = 40; app.refresh_workspace(); app.update(); app.update()
    ws = top_widgets(app)
    check("window now starts past the top", ws[0].index == 40)
    drop_named("LATE", (mid(ws[3]) + mid(ws[4])) // 2)
    check("drop in a late window inserts at ABSOLUTE index 44", big2["blocks"][44][1]["variable"] == "LATE" and big2["blocks"][43][1]["variable"] == "v43")

    # ---- indicator line + palette item plumbing ----
    open_node(app, tab, node); ws = top_widgets(app)
    app.show_drop_indicator(0, (mid(ws[1]) + mid(ws[2])) // 2); app.update()
    line = app._drop_line
    check("indicator created and placed", line is not None and line.winfo_exists() and line.winfo_ismapped())
    app.show_drop_indicator(0, mid(ws[3]) - 2); app.update()
    check("indicator reuses the same widget while moving", app._drop_line is line)
    app.show_drop_indicator(None, None); app.update()
    check("indicator removed on clear", app._drop_line is None)
    app.show_drop_indicator(None, None)  # clearing twice is harmless
    # a real drag over the workspace shows the line, and the release removes it
    probe = PaletteBlockItem(app.palette_frame, mod, lambda m: None, app.can_drop_block_at,
                             lambda m, x, y: None, app.show_drop_indicator)
    app.update(); qx, qy = probe.winfo_rootx() + 5, probe.winfo_rooty() + 5
    probe._drag_press(NS(x_root=qx, y_root=qy)); probe._drag_motion(NS(x_root=qx + 30, y_root=qy + 30))
    probe._drag_motion(NS(x_root=app.workspace_canvas.winfo_rootx() + 200, y_root=mid(ws[1]))); app.update()
    check("dragging over the workspace shows the line", app._drop_line is not None and app._drop_line.winfo_exists())
    probe._drag_release(NS(x_root=app.workspace_canvas.winfo_rootx() + 200, y_root=mid(ws[1]))); app.update()
    check("releasing removes the line", app._drop_line is None)
    probe.destroy()

    calls = []
    item = PaletteBlockItem(app.palette_frame, mod, lambda m: calls.append(("add", None)),
                            app.can_drop_block_at,
                            lambda m, x, y: calls.append(("drop", y)),
                            lambda x, y: calls.append(("fb", x)))
    app.update()
    px, py = item.winfo_rootx() + 5, item.winfo_rooty() + 5
    wx = app.workspace_canvas.winfo_rootx() + 200
    wy = mid(ws[2])
    item._drag_press(NS(x_root=px, y_root=py)); item._drag_motion(NS(x_root=px + 30, y_root=py + 30))
    item._drag_motion(NS(x_root=wx, y_root=wy)); app.update()
    check("hover over workspace sends feedback with coordinates", ("fb", wx) in calls)
    item._drag_motion(NS(x_root=px, y_root=py)); app.update()
    check("hover over invalid target clears feedback", ("fb", None) in calls)
    item._drag_release(NS(x_root=wx, y_root=wy)); app.update()
    check("release over workspace calls on_drop with the position", ("drop", wy) in calls and ("add", None) not in calls)
    check("release clears the feedback line", calls[-2] == ("fb", None) or ("fb", None) in calls[-3:])
    del calls[:]
    item._drag_press(NS(x_root=px, y_root=py)); item._drag_motion(NS(x_root=px + 30, y_root=py + 30))
    item._drag_motion(NS(x_root=wx, y_root=wy)); app.update()
    calls.append(("mark", None))
    item._drag_release(NS(x_root=wx, y_root=wy)); app.update()
    after = calls[calls.index(("mark", None)):]
    check("release always clears the feedback line (even over a valid target)", ("fb", None) in after)
    n0 = len(calls)
    item._drag_press(NS(x_root=px, y_root=py)); item._drag_release(NS(x_root=px, y_root=py)); app.update()
    check("plain click still calls on_add, not on_drop", ("add", None) in calls[n0:] and not any(c[0] == "drop" for c in calls[n0:]))
    n1 = len(calls)
    item._drag_press(NS(x_root=px, y_root=py)); item._drag_motion(NS(x_root=px + 40, y_root=py + 40))
    item._drag_release(NS(x_root=px + 40, y_root=py + 40)); app.update()
    check("release over an invalid target adds nothing", not any(c[0] in ("add", "drop") for c in calls[n1:]))

    # real Tk-delivered drag through the item the palette actually built
    real_add = app.add_block_to_workspace
    seen = []
    app.add_block_to_workspace = lambda m, c=None, insert_at=None: seen.append(insert_at)
    try:
        real_items = [w for w in all_descendants(app.palette_frame) if isinstance(w, PaletteBlockItem) and w is not item]
        check("palette items are wired to the drop handler", real_items and all(i.on_drop == app.add_block_from_drop for i in real_items))
        it = real_items[0]; app.update()
        sx, sy = it.winfo_rootx() + 5, it.winfo_rooty() + 5
        it._drag_press(NS(x_root=sx, y_root=sy)); it._drag_motion(NS(x_root=sx + 30, y_root=sy + 30))
        it._drag_release(NS(x_root=wx, y_root=(mid(ws[1]) + mid(ws[2])) // 2)); app.update()
        check("palette-built item drops at the computed index", seen == [2])
    finally:
        app.add_block_to_workspace = real_add

    app.destroy()
    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)

main()
