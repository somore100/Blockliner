"""Dragging from an output port to another node adds the ready-made call to the
TARGET node (data direction); click on the dot still opens the colour menu.
Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def fn(name, params, ret):
    kids = [("return_statement", {"value": ret})] if ret is not None else [("print_output", {"value": "1"})]
    return make_node(name, node_id=name, blocks=[("func_def", {"name": name, "params": params, "_children": kids})])

def dots(w, side_name):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, tk.Label) and ch.cget("text") == "●": out.append(ch)
        out += dots(ch, side_name)
    return out

def build():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = [fn("verify", "username, password", "approved, declined"),
             fn("gen_pw", "", "text"),
             fn("noret", "x", None),
             fn("weird", "", "user, None"),
             make_node("ui", node_id="ui", blocks=[("print_output", {"value": "'hi'"})]),
             make_node("ui2", node_id="ui2", blocks=[("print_output", {"value": "'hi'"})])]
    for i, n in enumerate(nodes):
        n["canvas_x"], n["canvas_y"] = 20 + (i % 3) * 300, 20 + (i // 3) * 260
    tab["nodes"] = nodes; tab["active_node_id"] = "ui"; tab["file_view_path"] = []
    app.project_blocks = find_node_by_id(nodes, "ui")["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update(); app.update()
    return app, tab

def ev_over(app, node_id, dx=10, dy=10):
    """A mouse event whose root position is inside that node's box."""
    n = find_node_by_id(app.tabs[app.active_tab_index]["nodes"], node_id)
    cv = app.workspace_canvas
    return types.SimpleNamespace(
        x_root=int(cv.winfo_rootx() + n["canvas_x"] * app.canvas_zoom - cv.canvasx(0) + dx),
        y_root=int(cv.winfo_rooty() + n["canvas_y"] * app.canvas_zoom - cv.canvasy(0) + dy), widget=None)

def main():
    app, tab = build()
    nodes = tab["nodes"]
    ui = find_node_by_id(nodes, "ui")

    # ---- two outputs -> one tuple assignment with the inputs as arguments
    check("add_port_wire reports success", app.add_port_wire("verify", "ui"))
    blk = ui["blocks"][-1]
    check("assignment of all outputs added to the TARGET", blk[0] == "assign_variable" and blk[1]["variable"] == "approved, declined")
    chip = blk[1]["value"]
    check("value is a call chip of the source with its inputs as args",
          chip == {"_nested_block": "func_call", "_nested_params": {"name": "verify", "args": "username, password"}})
    code = app.generate_code_for_tab(tab, "python")
    check("generated code reads like a call", "approved, declined = verify(username, password)" in code)
    check("source node is untouched", len(find_node_by_id(nodes, "verify")["blocks"]) == 1)
    app.recompute_references()
    check("wire is derived: ui calls verify", "verify" in [find_node_by_id(nodes, r)["name"] if find_node_by_id(nodes, r) else r
                                                           for r in (ui.get("references") or [])])

    # ---- single output
    app.add_port_wire("gen_pw", "ui2")
    b2 = find_node_by_id(nodes, "ui2")["blocks"][-1]
    check("single output -> text = gen_pw()", b2[0] == "assign_variable" and b2[1]["variable"] == "text"
          and b2[1]["value"]["_nested_params"] == {"name": "gen_pw", "args": ""})

    # ---- no return value -> plain call block
    app.add_port_wire("noret", "ui2")
    b3 = find_node_by_id(nodes, "ui2")["blocks"][-1]
    check("no outputs -> plain func_call block", b3 == ("func_call", {"name": "noret", "args": "x"}))

    # ---- a returned value that is not a name (None) -> plain call, never broken code
    app.add_port_wire("weird", "ui2")
    b4 = find_node_by_id(nodes, "ui2")["blocks"][-1]
    check("non-name output falls back to a plain call", b4[0] == "func_call" and b4[1]["name"] == "weird")
    check("no invalid 'None =' code generated", "None =" not in app.generate_code_for_tab(tab, "python")
          and "None, " not in app.generate_code_for_tab(tab, "python").split("weird")[0].split("\n")[-1])

    # ---- the real gesture: press on the dot, release over a node
    app.switch_to_file_view(); app.update(); app.update()
    ui2 = find_node_by_id(nodes, "ui2"); before = len(ui2["blocks"])
    box = app._fileview_boxes["gen_pw"][1]
    import node_ports as _np
    palette = {c for _, c in _np.PORT_COLORS}
    outdots = [d for d in dots(box, "out") if d.cget("cursor") == "crosshair" and d.cget("fg") in palette]
    check("output dot is a drag handle", len(outdots) == 1)
    press = ev_over(app, "gen_pw", 5, 5)
    app._oport_press(press, "gen_pw", "text")
    check("drag started in output mode", app._wire_drag_source == "gen_pw" and app._wire_drag_mode == ("out", "text"))
    app._port_release(ev_over(app, "ui2", 30, 30)); app.update()
    check("release over a node adds the call there", len(find_node_by_id(nodes, "ui2")["blocks"]) == before + 1)
    check("drag state is cleared", app._wire_drag_source is None and getattr(app, "_wire_drag_mode", None) is None)

    # ---- release on empty canvas: nothing added, no node-creation menu
    shown = []
    app.show_drop_menu = lambda *a, **k: shown.append(a)
    popped = []
    app._popup = lambda menu, e: popped.append(menu)
    n_before = len(nodes); blocks_before = sum(len(n["blocks"]) for n in nodes)
    p = ev_over(app, "gen_pw", 5, 5)
    app._oport_press(p, "gen_pw", "text")
    far = types.SimpleNamespace(x_root=p.x_root + 700, y_root=p.y_root + 500, widget=None)
    app._port_release(far)
    check("empty canvas cancels (no node menu, nothing added)",
          not shown and len(nodes) == n_before and sum(len(n["blocks"]) for n in nodes) == blocks_before)

    # ---- a click that never leaves the dot opens the colour menu
    p = ev_over(app, "gen_pw", 5, 5)
    app._oport_press(p, "gen_pw", "text"); app._port_release(p)
    check("plain click opens the colour menu", len(popped) == 1)
    check("and adds nothing", sum(len(n["blocks"]) for n in nodes) == blocks_before)

    # ---- input dots keep their click-to-colour behaviour
    vbox = app._fileview_boxes["verify"][1]
    check("input dots are not drag handles", len([d for d in dots(vbox, "in") if d.cget("cursor") == "hand2"]) >= 2)

    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
