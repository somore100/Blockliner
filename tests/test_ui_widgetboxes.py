"""Scripted UI test (run under Xvfb): a UI window's widgets as separate draggable boxes on the Nodes layer: one box per
widget, a wire from each linked event to its function, dragging moves a box (and the wire), the window carries its
boxes along, the positions are saved, a dot makes a function beside its box, switching back removes the boxes."""
import os, sys, time
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI
import ui_node, project_file
from nodes_model import find_node_by_id

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def settle(app, sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.update_idletasks(); app.update(); time.sleep(0.01)

def labels(widget):
    out = []
    for w in widget.winfo_children():
        try:
            out.append(w.cget("text"))
        except Exception:
            pass
        out += labels(w)
    return out

def main():
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1300x800+0+0")
    app.ask_ui_pack = lambda packs: packs[0]
    try:
        settle(app)
        pack = app.ui_pack_for("python")
        node = app.create_starter_node("ui", (60, 60))
        app.open_node(node["id"]); settle(app)
        ed = app.designer_editor
        root_id = ui_node.load_tree(node, pack).root["id"]
        for typ in ("button", "label"):
            ed.state["sel"] = root_id
            ed._dz_add_type(typ); settle(app, 0.1)
        tree = ui_node.load_tree(node, pack)
        btn = next(n for n in tree.walk() if n["type"] == "button")
        lab = next(n for n in tree.walk() if n["type"] == "label")
        app.goto_layer("nodes"); settle(app)
        app.toggle_ui_boxes(node["id"]); settle(app)
        reg = app.widget_boxes()
        check("boxes mode is on the node", node.get("ui_open") == "boxes")
        check("one box per widget", {k[1] for k in reg} == {btn["id"], lab["id"]})
        check("no list inside the window's box", not any(btn["name"] in str(t) for t in labels(app._fileview_boxes[node["id"]][1])))
        wx = app.workspace_canvas.coords(reg[(node["id"], btn["id"])][0])[0]
        check("the boxes sit right of the window", wx > node["canvas_x"] * app.canvas_zoom + 200)
        check("a dotted tie to the window", bool(app.workspace_canvas.find_withtag("uiwire")))

        hid = app.link_new_ui_handler(node["id"], btn["id"], "command"); settle(app)
        handler = find_node_by_id(app.tabs[app.active_tab_index]["nodes"], hid)
        reg = app.widget_boxes()
        check("the boxes survive the refresh", (node["id"], btn["id"]) in reg)
        bx, by = app.widget_box_origin(node, btn["id"])
        check("the new function sits beside the widget's box", abs(handler["canvas_x"] - (bx + 280)) < 1 and abs(handler["canvas_y"] - by) < 1)
        n_before = len(app.workspace_canvas.find_withtag("uiwire"))
        check("a wire runs from the event to the function", n_before >= 3)

        # drag the button's box
        head = reg[(node["id"], btn["id"])][1].winfo_children()[0]
        rx, ry = head.winfo_rootx() + 5, head.winfo_rooty() + 5
        head.event_generate("<ButtonPress-1>", x=5, y=5, rootx=rx, rooty=ry); settle(app, 0.05)
        for k in range(1, 6):
            head.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 20 * k, rooty=ry + 10 * k); settle(app, 0.02)
        head.event_generate("<ButtonRelease-1>", x=5, y=5, rootx=rx + 100, rooty=ry + 50); settle(app, 0.05)
        nx, ny = app.widget_box_origin(node, btn["id"])
        check("dragging moved the box", abs((nx - bx) / 1 - 100 / app.canvas_zoom) < 3 and abs((ny - by) - 50 / app.canvas_zoom) < 3)
        check("the new place is saved as an offset", node["ui_box_pos"][btn["id"]][0] > 0)
        check("the window is marked changed", app.tabs[app.active_tab_index].get("dirty", True))

        # the function's blocks show inside the box
        import ui_widgetboxes
        pv = ui_widgetboxes.preview_of("a = 1\n\nprint(a)\n" + "x\n" * 6)
        check("preview: five lines and a count", len(pv) == 6 and pv[-1] == "+ 3 more lines")
        check("preview: long lines are cut", len(ui_widgetboxes.preview_of("y" * 100)[0]) == ui_widgetboxes.PREVIEW_CHARS)
        before_y = app.workspace_canvas.coords(app.widget_boxes()[(node["id"], lab["id"])][0])[1]
        handler["blocks"].extend([("print_output", {"value": f"'step {i}'"}) for i in range(7)])
        app.refresh_workspace(); settle(app)
        boxw = app.widget_boxes()[(node["id"], btn["id"])][1]
        texts = [str(t) for t in labels(boxw)]
        check("the function's code is shown in the widget's box", any("step 0" in t for t in texts))
        check("... only the first lines, with a count", not any("step 6" in t for t in texts) and any("more lines" in t for t in texts))
        check("... and the next box makes room", lab["id"] in {k[1] for k in app.widget_boxes()} and
              app.workspace_canvas.coords(app.widget_boxes()[(node["id"], lab["id"])][0])[1] > before_y + 40)

        # the window carries its boxes
        node["canvas_x"] += 100
        app.place_widget_boxes(node["id"]); settle(app, 0.05)
        check("moving the window moves the boxes", abs(app.widget_box_origin(node, btn["id"])[0] - (nx + 100)) < 1)

        saved = project_file.dumps("python", [node], node["id"])
        _l, loaded, _a, _n = project_file.parse_project_data(__import__("json").loads(saved), ["python"])
        check("mode and places survive save and load", loaded[0].get("ui_open") == "boxes" and
              loaded[0].get("ui_box_pos", {}).get(btn["id"]) == node["ui_box_pos"][btn["id"]])

        # a refresh and a zoom keep the boxes
        app.refresh_workspace(); settle(app)
        check("a full refresh rebuilds them", len(app.widget_boxes()) == 2)
        app.set_zoom(0.7); settle(app, 0.4)
        check("zooming keeps them", len(app.widget_boxes()) == 2)
        app.set_zoom(1.0); settle(app, 0.4)

        # list mode and closing
        app.toggle_ui_widgets(node["id"]); settle(app)
        check("list mode replaces the boxes", node.get("ui_open") is True and not app.widget_boxes())
        app.toggle_ui_boxes(node["id"]); settle(app)
        app.toggle_ui_boxes(node["id"]); settle(app)
        check("switching boxes off removes them", "ui_open" not in node and not app.widget_boxes() and
              not app.workspace_canvas.find_withtag("uiwire"))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
