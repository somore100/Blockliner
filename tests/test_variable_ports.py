"""Nodes WITHOUT a function: output ports = variables assigned at top level;
dragging one adds a print (node) or "<input> = <variable>" (input port) to the
target. Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import node_ports as np_
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def var_node(name, *assigns, extra=()):
    blocks = [("assign_variable", {"variable": v, "value": val}) for v, val in assigns] + list(extra)
    return make_node(name, node_id=name, blocks=blocks)

def fn(name, params, ret):
    return make_node(name, node_id=name, blocks=[("func_def", {"name": name, "params": params,
            "_children": [("return_statement", {"value": ret})]})])

def centre(w): return w.winfo_rootx() + w.winfo_width() // 2, w.winfo_rooty() + w.winfo_height() // 2
def ev(x, y): return types.SimpleNamespace(x_root=x, y_root=y, widget=None)

def texts(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, (tk.Label, tk.Button)): out.append(str(ch.cget("text")))
        out += texts(ch)
    return out

def drag(app, src, name, xy):
    sx, sy = centre(app._fileview_boxes[src][1]); sx -= 40
    app._oport_press(ev(sx, sy), src, name); app._port_motion(ev(*xy)); app._port_release(ev(*xy)); app.update()

def main():
    # ---- pure
    n = var_node("gen", ("text", "make()"), ("a, b", "f()"), ("1bad", "x"), ("class", "y"), ("text", "again"))
    check("outputs are the assigned names, in order, no duplicates/invalid",
          np_.node_interface(n) == ([], ["text", "a", "b"]))
    check("tuple assignment gives one port per name", np_.assigned_names(var_node("t", ("a, b", "f()"))) == ["a", "b"])
    nested = make_node("n", node_id="n", blocks=[("if_statement", {"condition": "x", "_children": [("assign_variable", {"variable": "inner", "value": "1"})]})])
    check("only TOP-LEVEL assignments count", np_.node_interface(nested) == ([], []))
    check("no assignments, no ports", np_.node_ports(make_node("p", node_id="p", blocks=[("print_output", {"value": "1"})])) == [])
    both = fn("verify", "u", "ok"); both["blocks"].append(("assign_variable", {"variable": "extra", "value": "1"}))
    check("a node WITH its function keeps function ports only", np_.node_interface(both) == (["u"], ["ok"]))
    check("class/category never get variable ports", np_.node_interface(make_node("c", kind="category")) == ([], []))
    check("junk blocks do not crash", np_.node_interface(make_node("j", node_id="j", blocks=[None, ("assign_variable", None), ("assign_variable", {"variable": 3})])) == ([], []))
    check("has_function", np_.has_function(fn("f", "", "1")) and not np_.has_function(n))
    pc = np_.node_ports(n)
    check("ports are outputs with colours", [p["side"] for p in pc] == ["out"] * 3 and all(p["color"] for p in pc))

    # ---- UI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = [var_node("gen_pw", ("text", "'abc'")), fn("check_pw", "password", "ok"),
             make_node("ui", node_id="ui", blocks=[("print_output", {"value": "'hi'"})]),
             make_node("ui2", node_id="ui2", blocks=[("print_output", {"value": "'hi'"})])]
    for i, nd in enumerate(nodes): nd["canvas_x"], nd["canvas_y"] = 20 + (i % 4) * 330, 20
    tab["nodes"] = nodes; tab["active_node_id"] = "ui"; tab["file_view_path"] = []
    app.project_blocks = find_node_by_id(nodes, "ui")["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update(); app.update()
    code = lambda: app.generate_code_for_tab(tab, "python")

    box = app._fileview_boxes["gen_pw"][1]
    check("node box shows the variable as an output port", "text" in texts(box))
    palette = {c for _, c in np_.PORT_COLORS}
    def dots(w):
        o = []
        for ch in w.winfo_children():
            if isinstance(ch, tk.Label) and ch.cget("text") == "●" and ch.cget("fg") in palette: o.append(ch)
            o += dots(ch)
        return o
    check("its dot is a drag handle", [d.cget("cursor") for d in dots(box)] == ["crosshair"])

    ui = find_node_by_id(nodes, "ui"); n0 = len(ui["blocks"])
    ux, uy = app._fileview_boxes["ui"][1].winfo_rootx() + 6, app._fileview_boxes["ui"][1].winfo_rooty() + app._fileview_boxes["ui"][1].winfo_height() - 6
    drag(app, "gen_pw", "text", (ux, uy))
    check("drop on a node adds a print of the variable", len(ui["blocks"]) == n0 + 1 and ui["blocks"][-1] == ("print_output", {"value": "text"}))
    check("source node untouched", len(find_node_by_id(nodes, "gen_pw")["blocks"]) == 1)
    check("generated code: assignment then print", "text = 'abc'" in code() and "print(text)" in code())

    chk = find_node_by_id(nodes, "check_pw")
    line = app._fileview_boxes["check_pw"][1]._in_port_lines[0][1]
    drag(app, "gen_pw", "text", centre(line))
    check("drop on an input port assigns it", chk["blocks"][-1] == ("assign_variable", {"variable": "password", "value": "text"}))

    # ---- drop on empty canvas cancels; click opens the colour menu
    total = sum(len(x["blocks"]) for x in nodes)
    p = centre(app._fileview_boxes["gen_pw"][1]); app._oport_press(ev(p[0] - 40, p[1]), "gen_pw", "text")
    app._port_release(ev(p[0] + 900, p[1] + 600)); app.update()
    check("release on empty canvas adds nothing", sum(len(x["blocks"]) for x in nodes) == total)
    popped = []; app._popup = lambda m, e: popped.append(m)
    app._oport_press(ev(p[0] - 40, p[1]), "gen_pw", "text"); app._port_release(ev(p[0] - 40, p[1]))
    check("plain click opens the colour menu", len(popped) == 1)

    # ---- add_port_wire directly
    check("a node with no variables cannot be dragged from", app.add_port_wire("ui2", "ui") is False)
    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
