"""Node ports: inputs = parameters / outputs = returned values of a def named
like the node; auto colours + manual override; shown on the node box; saved
in the project file and the sidecar. Headless (Xvfb)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import node_ports as np_
import project_file, portable
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def fn(name, params, ret_blocks, extra=None):
    d = ("func_def", {"name": name, "params": params, "_children": ret_blocks})
    return make_node(name, node_id=name, blocks=[d] + (extra or []))

def texts(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, tk.Label): out.append((ch.cget("text"), str(ch.cget("fg"))))
        out += texts(ch)
    return out

def pure():
    check("params: plain/default/star/annotation/c-style",
          np_.param_names("a, b=1, *args, c: int, int d") == ["a", "b", "args", "c", "d"])
    check("params: self/cls skipped, empty ok", np_.param_names("self, x") == ["x"] and np_.param_names("") == [])
    check("params: comma inside a default is not a split", np_.param_names("a=(1, 2), b") == ["a", "b"])
    check("returns: two values", np_.return_names("user, error") == ["user", "error"])
    check("returns: tuple parens", np_.return_names("(a, b)") == ["a", "b"])
    check("returns: one call keeps its inner comma", np_.return_names("f(a, b)") == ["f(a, b)"])
    check("returns: empty", np_.return_names("") == [])
    check("returns: long name shortened", len(np_.return_names("x" * 60)[0]) == np_.MAX_NAME)

    n = fn("verify", "username, password",
           [("if_statement", {"cond": "ok", "_children": [("return_statement", {"value": "user, None"})]}),
            ("return_statement", {"value": "None, error"})])
    check("interface reads params and nested returns",
          np_.node_interface(n) == (["username", "password"], ["user", "None", "error"]))
    n2 = fn("other", "a", [("return_statement", {"value": "a"})])
    n2["name"] = "renamed"
    check("def must be named like the node", np_.node_interface(n2) == ([], []))
    check("no def, no ports", np_.node_ports(make_node("plain", node_id="plain",
          blocks=[("print_output", {"value": "1"})])) == [])
    check("class/category never have ports", np_.node_interface(make_node("c", kind="category")) == ([], []))
    check("junk blocks do not crash", np_.node_interface(make_node("j", node_id="j", blocks=[None, ("func_def", None), ("x",)])) == ([], []))

    ports = np_.node_ports(n)
    check("inputs listed before outputs", [p["side"] for p in ports] == ["in", "in", "out", "out", "out"])
    cols_out = [p["color"] for p in ports if p["side"] == "out"]
    check("ports on one side get different colours", len(set(cols_out)) == len(cols_out))
    a = np_.auto_color("user"); check("auto colour is stable", a == np_.auto_color("user"))
    check("same name in and out matches colour",
          np_.node_ports(fn("p", "user", [("return_statement", {"value": "user"})]))[0]["color"]
          == np_.node_ports(fn("p", "user", [("return_statement", {"value": "user"})]))[1]["color"])

    np_.set_port_color(n, "out", "user", "#112233")
    p = [x for x in np_.node_ports(n) if x["name"] == "user"][0]
    check("manual colour wins and is flagged", p["color"] == "#112233" and p["manual"])
    check("manual colour does not repeat on a sibling", len({x["color"] for x in np_.node_ports(n) if x["side"] == "out"}) == 3)
    np_.set_port_color(n, "out", "user", "not a colour")
    check("invalid colour = back to automatic, key removed", "port_colors" not in n)
    check("clean_port_colors drops junk",
          np_.clean_port_colors({"in:a": "#aabbcc", "out:b": "red", "x:c": "#aabbcc", 3: "#aabbcc"}) == {"in:a": "#aabbcc"})

def ui():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    v = fn("verify", "username, password", [("return_statement", {"value": "approved, declined"})])
    plain = make_node("plain", node_id="plain", blocks=[("print_output", {"value": "'x'"})])
    tab["nodes"] = [v, plain]; tab["active_node_id"] = "plain"; tab["file_view_path"] = []
    v["canvas_x"], v["canvas_y"] = 20, 20; plain["canvas_x"], plain["canvas_y"] = 400, 20
    app.project_blocks = plain["blocks"]; normalize_orders(tab["nodes"])
    app.switch_to_file_view(); app.update(); app.update()

    t = texts(app._fileview_boxes["verify"][1]); names = [x[0] for x in t]
    check("box shows input names", "username" in names and "password" in names)
    check("box shows output names", "approved" in names and "declined" in names)
    check("box shows one dot per port", names.count("●") >= 4)
    check("node without a def shows no port names", "username" not in [x[0] for x in texts(app._fileview_boxes["plain"][1])])
    palette = {c for _, c in np_.PORT_COLORS}
    dots = [c for n, c in t if n == "\u25cf" and c in palette]
    check("dots carry palette colours", len(dots) >= 4)

    m = app.build_port_color_menu("verify", "out", "approved")
    labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) != "separator"]
    check("colour menu lists the palette and Automatic", "Red" in labels and "Automatic" in labels)
    app.set_port_color("verify", "out", "approved", "#ff0000"); app.update(); app.update()
    t = texts(app._fileview_boxes["verify"][1])
    check("colour change is drawn", ("●", "#ff0000") in t)
    check("colour change marks the file dirty", tab.get("dirty"))
    check("colour stored on the node", find_node_by_id(tab["nodes"], "verify")["port_colors"] == {"out:approved": "#ff0000"})
    gen = app.generate_code_for_tab(tab, "python")
    check("generated code is untouched by ports", "def verify(username, password):" in gen and "#ff0000" not in gen)

    # ---- save / load
    data = json.loads(project_file.dumps_workspace([{"title": "t", "language": "python", "nodes": tab["nodes"], "active_node_id": "plain"}], 0))
    files, _, _ = project_file.parse_workspace_data(data, ["python"], "python")
    check("colour survives project save/load", find_node_by_id(files[0]["nodes"], "verify").get("port_colors") == {"out:approved": "#ff0000"})
    data["files"][0]["nodes"][0]["port_colors"] = {"out:x": "banana", "in:y": "#00ff00"}
    files, _, _ = project_file.parse_workspace_data(data, ["python"], "python")
    check("bad stored colours are dropped on load", find_node_by_id(files[0]["nodes"], "verify").get("port_colors") == {"in:y": "#00ff00"})

    # ---- sidecar / embedded metadata
    meta = portable.build_metadata(tab["nodes"], "python", "plain")
    check("metadata carries the colour", meta["nodes"]["verify"].get("port_colors") == {"out:approved": "#ff0000"})
    check("metadata leaves out nodes without colours", "port_colors" not in meta["nodes"]["plain"])
    token = app.get_comment_token("python")
    text = app.generate_portable_for_tab(tab, "python", embed_meta=True)
    top, active, diag = portable.rebuild_nodes(text, "python")
    got = {n["id"]: n for n in top}
    check("colour survives the embedded round trip", got["verify"].get("port_colors") == {"out:approved": "#ff0000"})
    meta["nodes"]["verify"]["port_colors"] = {"out:a": "oops", "in:b": "#0000ff"}
    top, _, _ = portable.rebuild_nodes(portable.strip_portable(text), "python", meta_override=meta)
    check("bad colours in metadata are dropped", {n["id"]: n for n in top}["verify"].get("port_colors") == {"in:b": "#0000ff"})
    app.destroy()

pure(); ui()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
