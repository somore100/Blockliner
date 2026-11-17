"""Scripted UI test (run under Xvfb): a UI window's box on the Nodes layer opens to its widgets, each event has a dot,
an empty dot makes and links a function, wires start at the dots, the function's box names who runs it, clicking a
widget opens the designer on it, and the open/closed state is saved."""
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
        app.goto_layer("nodes"); settle(app)
        box = app._fileview_boxes[node["id"]][1]
        check("closed: no widget list yet", not any(btn["name"] in str(t) for t in labels(box)))
        app.toggle_ui_widgets(node["id"]); settle(app)
        box = app._fileview_boxes[node["id"]][1]
        text = labels(box)
        check("opened: the widgets are listed", any(btn["name"] in str(t) for t in text))
        check("opened: the button's event has an empty dot", any("On click +" in str(t) for t in text))
        check("the open state is on the node", node.get("ui_open") is True)
        saved = project_file.dumps("python", [node], node["id"])
        _lang, loaded, _a, _n = project_file.parse_project_data(__import__("json").loads(saved), ["python"])
        check("... and survives save and load", loaded[0].get("ui_open") is True)

        hid = app.link_new_ui_handler(node["id"], btn["id"], "command"); settle(app)
        tab = app.tabs[app.active_tab_index]
        handler = find_node_by_id(tab["nodes"], hid)
        check("a function was made and named after the widget", handler is not None and handler["name"] == f"on_{btn['name']}_command")
        check("the widget's event points at it", ui_node.load_tree(node, pack).find(btn["id"])["events"].get("command") == hid)
        box = app._fileview_boxes[node["id"]][1]
        check("the dot is filled and shows the function", any(f"On click → {handler['name']}" in str(t) for t in labels(box)))
        offs = app.ui_port_offsets(node["id"], hid)
        check("the wire starts at the dot, not the middle of the box", len(offs) == 1 and 36 < offs[0] < box.winfo_height())
        check("a wire is drawn", bool(app.workspace_canvas.find_withtag(f"wire_{node['id']}_{hid}")))
        hbox = app._fileview_boxes[hid][1]
        check("the function's box says which widget runs it", any(f"{node['name']}.{btn['name']}" in str(t) for t in labels(hbox)))

        app.toggle_ui_widgets(node["id"]); settle(app)
        check("closed again: the wire goes back to the box", app.ui_port_offsets(node["id"], hid) == [] and
              bool(app.workspace_canvas.find_withtag(f"wire_{node['id']}_{hid}")))

        app.open_ui_widget(node["id"], btn["id"]); settle(app)
        check("clicking a widget opens the designer with it selected", app.designer_editor.state.get("sel") == btn["id"])
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
