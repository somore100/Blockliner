"""Ignore (right-click), Shift+right-click multi-select + move together, id vs order
display, popup lifetime, palette hidden on Files layer, zoom preview. Headless (Xvfb)."""
import os, sys, types, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import project_file
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def labels(menu): return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
def texts(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, tk.Label): out.append(ch.cget("text"))
        out += texts(ch)
    return out
def header_of(box):
    for ch in box.winfo_children():
        if ch.bind("<B1-Motion>"): return ch

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    a = make_node("alpha", node_id="a1", blocks=[("print_output", {"value": "'AAA'"})])
    b = make_node("beta", node_id="b1", blocks=[("print_output", {"value": "'BBB'"})])
    c = make_node("gamma", node_id="c1", blocks=[("print_output", {"value": "'CCC'"})])
    tab["nodes"] = [a, b, c]; tab["active_node_id"] = "a1"; tab["file_view_path"] = []
    a["canvas_x"], a["canvas_y"] = 20, 20; b["canvas_x"], b["canvas_y"] = 300, 20; c["canvas_x"], c["canvas_y"] = 20, 250
    app.project_blocks = a["blocks"]; normalize_orders(tab["nodes"])
    app.switch_to_file_view(); app.update(); app.update()

    # ---- id and order are two different things on the box
    t = texts(app._fileview_boxes["b1"][1])
    check("order badge shows the run order", "▶2" in t)
    check("id shown separately", "id b1" in t)

    # ---- ignore
    full = app.generate_code_for_tab(tab, "python")
    check("all three nodes generate code", all(s in full for s in ("AAA", "BBB", "CCC")))
    check("node menu offers Ignore", "Ignore" in labels(app.build_node_menu("b1")))
    app.toggle_ignore_node("b1"); app.update()
    code = app.generate_code_for_tab(tab, "python")
    check("ignored node is left out of generated code", "BBB" not in code and "AAA" in code and "CCC" in code)
    check("node is flagged and still in the project", b.get("ignored") is True and find_node_by_id(tab["nodes"], "b1"))
    check("menu now offers Stop ignoring", "Stop ignoring" in labels(app.build_node_menu("b1")))
    check("box shows it is ignored", any("ignored" in s for s in texts(app._fileview_boxes["b1"][1])))
    data = json.loads(project_file.dumps_workspace([{"title": "t", "language": "python", "nodes": tab["nodes"], "active_node_id": "a1"}], 0))
    files, _, _ = project_file.parse_workspace_data(data, ["python"], "python")
    check("ignored survives save/load", find_node_by_id(files[0]["nodes"], "b1").get("ignored") is True
          and not find_node_by_id(files[0]["nodes"], "a1").get("ignored"))
    app.toggle_ignore_node("b1"); app.update()
    check("un-ignore brings the code back", "BBB" in app.generate_code_for_tab(tab, "python") and "ignored" not in b)

    # ---- Shift+right-click selects; plain right-click does not
    from ui_canvas import SELECT_COLOR
    shift = types.SimpleNamespace(state=1, x_root=0, y_root=0, widget=None)
    app._on_node_box_right_click(shift, "a1"); app._on_node_box_right_click(shift, "b1")
    check("two nodes selected", app.selected_nodes() == {"a1", "b1"})
    check("selected boxes are highlighted", str(app._fileview_boxes["a1"][1].cget("highlightbackground")).lower() == SELECT_COLOR)
    app._on_node_box_right_click(shift, "a1")
    check("shift+right-click again deselects", app.selected_nodes() == {"b1"})
    app._on_node_box_right_click(shift, "a1")
    posted = {}
    orig = tk.Menu.tk_popup; tk.Menu.tk_popup = lambda self_, x, y: posted.update(menu=self_)
    try:
        app._on_node_box_right_click(types.SimpleNamespace(state=0, x_root=5, y_root=5, widget=None), "c1")
    finally:
        tk.Menu.tk_popup = orig
    check("plain right-click opens the menu and keeps the selection", posted.get("menu") is not None and app.selected_nodes() == {"a1", "b1"})
    check("menu says how many are selected", any("2 selected" in l for l in labels(app.build_node_menu("a1"))))

    # ---- dragging a selected node moves every selected node
    app.update()
    hdr = header_of(app._fileview_boxes["a1"][1])
    ax, ay, bx, by, cx = a["canvas_x"], a["canvas_y"], b["canvas_x"], b["canvas_y"], c["canvas_x"]
    rx, ry = hdr.winfo_rootx() + 5, hdr.winfo_rooty() + 5
    hdr.event_generate("<ButtonPress-1>", x=5, y=5, rootx=rx, rooty=ry)
    hdr.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 40, rooty=ry + 20)
    hdr.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 80, rooty=ry + 30)
    hdr.event_generate("<ButtonRelease-1>", x=5, y=5, rootx=rx + 80, rooty=ry + 30)
    app.update()
    dxa, dya = a["canvas_x"] - ax, a["canvas_y"] - ay
    check("dragged node moved", dxa > 40 and dya > 15)
    check("other selected node moved by the same amount", abs((b["canvas_x"] - bx) - dxa) < 1e-6 and abs((b["canvas_y"] - by) - dya) < 1e-6)
    check("unselected node stayed", c["canvas_x"] == cx)
    # dragging an UNselected node moves only itself
    hdr2 = header_of(app._fileview_boxes["c1"][1]); rx, ry = hdr2.winfo_rootx() + 5, hdr2.winfo_rooty() + 5
    a1x = a["canvas_x"]
    hdr2.event_generate("<ButtonPress-1>", x=5, y=5, rootx=rx, rooty=ry)
    hdr2.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 50, rooty=ry + 10)
    hdr2.event_generate("<ButtonRelease-1>", x=5, y=5, rootx=rx + 50, rooty=ry + 10)
    check("dragging an unselected node moves only it", c["canvas_x"] > cx + 30 and a["canvas_x"] == a1x)
    # ignore applies to the whole selection
    app.toggle_ignore_node("a1")
    check("ignore applies to every selected node", a.get("ignored") and b.get("ignored") and not c.get("ignored"))
    app.toggle_ignore_node("a1")
    check("and so does stop-ignoring", not a.get("ignored") and not b.get("ignored"))
    # click on empty canvas clears; opening a node clears
    cv = app.workspace_canvas
    app._pan_active = True; app._pan_moved = False
    app._pan_release(types.SimpleNamespace())
    check("plain click on empty canvas clears the selection", app.selected_nodes() == set())

    # ---- popup lifetime
    m1 = app.build_node_menu("a1")
    app.popup_menu = app.popup_menu
    app._active_popup = m1
    app._dismiss_popup()
    check("dismiss clears the active popup", app._active_popup is None)
    app._active_popup = m1
    app._install_popup_guards()
    top = app.winfo_toplevel()
    top.event_generate("<Escape>")
    app.update()
    check("Escape closes a posted menu", app._active_popup is None)
    app._active_popup = m1
    app._on_any_press(types.SimpleNamespace(widget=cv))
    check("click elsewhere closes it too", app._active_popup is None)
    app._active_popup = m1
    app._on_any_press(types.SimpleNamespace(widget=m1))
    check("click on the menu itself keeps it", app._active_popup is m1)
    app._dismiss_popup()
    top_bound = top.bind("<Unmap>")
    check("window minimize (Unmap) is guarded", bool(top_bound))

    # ---- palette: only on the Blocks layer
    for layer, want in (("files", False), ("nodes", False), ("blocks", True)):
        app.goto_layer(layer); app.update(); app.update()
        check(f"palette visible on {layer} layer == {want}", app.panels.is_visible("palette") == want)
    app.goto_layer("nodes"); app.update()

    # ---- zoom: wheel steps collapse into ONE in-place resize, no rebuild
    app.set_zoom(1.0); app.update()
    calls, rescales = [], []
    orig_r, orig_s = app.rerender_canvas_layer, app.rescale_canvas_layer
    app.rerender_canvas_layer = lambda: (calls.append(1), orig_r())[1]
    app.rescale_canvas_layer = lambda: (rescales.append(1), orig_s())[1]
    box0 = app._fileview_boxes["a1"][1]
    w0 = box0.winfo_reqwidth()
    for _ in range(6): app.zoom_step(-1, 300, 200)
    check("zoom value follows the wheel at once", app.canvas_zoom > 1.5)
    check("nothing resized before the event loop runs", rescales == [])
    app.update()
    check("six wheel steps = exactly one resize", len(rescales) == 1)
    check("no rebuild at all while zooming", calls == [])
    check("the very same box widget is still shown", app._fileview_boxes["a1"][1] is box0 and box0.winfo_exists())
    check("boxes now drawn at the new size", box0.winfo_reqwidth() > w0 * 1.4)
    wx = app.workspace_canvas.coords(app._fileview_boxes["a1"][0])[0]
    check("box positions match the final zoom", abs(wx - a["canvas_x"] * app.canvas_zoom) < 1)
    app.rescale_canvas_layer = orig_s
    app.rerender_canvas_layer = orig_r
    app.set_zoom(1.0); app.update()

    app.destroy()
    print("\nFAILURES:", FAILURES if FAILURES else "none")
    sys.exit(1 if FAILURES else 0)

main()
