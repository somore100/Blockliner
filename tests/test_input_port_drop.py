"""Dropping an output port ON a specific input port of another node adds the
call to that node, stored in a variable named like the input port. Dropping on
the node body keeps the old behaviour. Headless (Xvfb)."""
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

def build():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = [fn("gen_pw", "", "text"), fn("verify", "username, password", "approved, declined"),
             fn("weird", "", "user, None"), fn("check_pw", "password, extra", "ok"),
             fn("check2", "password", "ok"), fn("check3", "password", "ok"),
             fn("check4", "password", "ok")]
    for i, n in enumerate(nodes):
        n["canvas_x"], n["canvas_y"] = 20 + (i % 4) * 330, 20 + (i // 4) * 300
    tab["nodes"] = nodes; tab["active_node_id"] = "gen_pw"; tab["file_view_path"] = []
    app.project_blocks = find_node_by_id(nodes, "gen_pw")["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update(); app.update()
    return app, tab

def centre(w):
    return w.winfo_rootx() + w.winfo_width() // 2, w.winfo_rooty() + w.winfo_height() // 2

def ev(x, y): return types.SimpleNamespace(x_root=x, y_root=y, widget=None)

def port_xy(app, node_id, name):
    for n, line in app._fileview_boxes[node_id][1]._in_port_lines:
        if n == name: return centre(line)
    raise KeyError(name)

def node_xy(app, node_id):
    w = app._fileview_boxes[node_id][1]
    return w.winfo_rootx() + 6, w.winfo_rooty() + w.winfo_height() - 6   # bottom-left corner, no port there

def drag(app, src, out_name, target_xy):
    sx, sy = centre(app._fileview_boxes[src][1]); sx -= 40
    app._oport_press(ev(sx, sy), src, out_name)
    app._port_motion(ev(*target_xy))
    app._port_release(ev(*target_xy)); app.update()

def main():
    app, tab = build(); nodes = tab["nodes"]
    code = lambda: app.generate_code_for_tab(tab, "python")
    chk = find_node_by_id(nodes, "check_pw")

    check("input ports are registered for hit-testing", [n for n, _ in app._fileview_boxes["check_pw"][1]._in_port_lines] == ["password", "extra"])

    # --- drop on the `password` port
    before = len(chk["blocks"])
    drag(app, "gen_pw", "text", port_xy(app, "check_pw", "password"))
    check("one block added to the node dropped on", len(chk["blocks"]) == before + 1)
    b = chk["blocks"][-1]
    check("variable is named like the input port", b[0] == "assign_variable" and b[1]["variable"] == "password"
          and b[1]["value"]["_nested_params"] == {"name": "gen_pw", "args": ""})
    check("generated code: password = gen_pw()", "password = gen_pw()" in code())
    check("source node untouched", len(find_node_by_id(nodes, "gen_pw")["blocks"]) == 1)

    # --- the other port picks the other name
    drag(app, "gen_pw", "text", port_xy(app, "check_pw", "extra"))
    check("dropping on `extra` names the variable extra", chk["blocks"][-1][1]["variable"] == "extra")

    # --- drop on the node body (no port): old behaviour, named like the output
    c2 = find_node_by_id(nodes, "check2")
    drag(app, "gen_pw", "text", node_xy(app, "check2"))
    check("node body drop keeps old naming", c2["blocks"][-1][1]["variable"] == "text")

    # --- several outputs: the dragged one is renamed, the others keep their names
    c3 = find_node_by_id(nodes, "check3")
    drag(app, "verify", "declined", port_xy(app, "check3", "password"))
    check("dragged output renamed, sibling kept", c3["blocks"][-1][1]["variable"] == "approved, password")
    check("generated code for two outputs", "approved, password = verify(username, password)" in code())
    c4 = find_node_by_id(nodes, "check4")
    drag(app, "verify", "approved", port_xy(app, "check4", "password"))
    check("first output renamed", c4["blocks"][-1][1]["variable"] == "password, declined")

    # --- a non-name output never produces broken code
    c5 = find_node_by_id(nodes, "check4"); n5 = len(c5["blocks"])
    drag(app, "weird", "None", port_xy(app, "check4", "password"))
    last = c5["blocks"][-1]
    check("non-name output -> plain call", len(c5["blocks"]) == n5 + 1 and last[0] == "func_call" and last[1]["name"] == "weird")
    check("no 'None =' in code", "None =" not in code())

    # --- hover highlight is shown while over a port and cleared afterwards
    px, py = port_xy(app, "check2", "password")
    sx, sy = centre(app._fileview_boxes["gen_pw"][1])
    app._oport_press(ev(sx - 40, sy), "gen_pw", "text"); app._port_motion(ev(px, py))
    hl = getattr(app, "_in_port_hl", None)
    check("input port highlighted while hovering", hl is not None and str(hl.cget("bg")) != "#1e1e1e" and hl.cget("bg") == "#1f4b52")
    n_blocks = sum(len(n["blocks"]) for n in nodes)
    app._port_release(ev(sx + 900, sy + 900)); app.update()
    check("highlight cleared after release", getattr(app, "_in_port_hl", None) is None)
    check("release on empty canvas adds nothing", sum(len(n["blocks"]) for n in nodes) == n_blocks)

    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
