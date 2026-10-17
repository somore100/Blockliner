"""Category OUTPUT ports: a category shows on its edge every output port of a
node inside it (any depth) that no OTHER inner node uses. Function node =
used when another inner node calls it; variable port = used when another inner
node reads it. Drag from such a port = the inner node is the real source;
colour menu belongs to the inner node. Headless (Xvfb)."""
import copy, json, os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import node_ports as np_
import project_file
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def fn(name, params="", ret="", **kw):
    kids = [("return_statement", {"value": ret})] if ret else []
    return make_node(name, node_id=name, blocks=[("func_def", {"name": name, "params": params, "_children": kids})], **kw)

def var_node(name, *assigns):
    return make_node(name, node_id=name, blocks=[("assign_variable", {"variable": v, "value": val}) for v, val in assigns])

def cat(name, *kids, **kw):
    return make_node(name, node_id=name, kind="category", child_nodes=list(kids), **kw)

def names(ports): return [p["label"] for p in ports]
def srcs(ports): return [p["src"] for p in ports]

def main():
    # ---------------- pure
    a = fn("a", "x", "res")
    check("a lone function node: its output shows, inputs never",
          names(np_.category_ports(cat("C", a))) == ["res"] and srcs(np_.category_ports(cat("C", a))) == ["a"])
    check("ports are outputs only", all(p["side"] == "out" for p in np_.category_ports(cat("C", fn("f", "p, q", "r, s")))))
    check("not a category = no ports", np_.category_ports(a) == [] and np_.category_ports(None) == []
          and np_.category_ports(make_node("k", kind="class")) == []
          and np_.category_ports(make_node("k", kind="class", child_nodes=[fn("m", "", "mm")])) == []
          and np_.category_ports(dict(fn("f", "", "r"), child_nodes=[fn("m", "", "mm")])) == [])
    check("empty category = no ports", np_.category_ports(cat("C")) == [])
    check("function without outputs = no port", np_.category_ports(cat("C", fn("v", "x", ""))) == [])

    caller = fn("caller", "", "done"); caller["references"] = ["a"]
    check("called by another inner node: hidden; the caller (unused) still shows",
          names(np_.category_ports(cat("C", a, caller))) == ["done"])
    a2 = fn("a", "x", "res"); a2["references"] = ["a"]
    check("a node calling itself does not hide itself", names(np_.category_ports(cat("C", a2))) == ["res"])
    outside = fn("outside", "", "o"); outside["references"] = ["a"]
    check("used only from OUTSIDE the category: still shown",
          names(np_.category_ports(cat("C", fn("a", "x", "res")))) == ["res"])
    caller2 = fn("caller", "", ""); caller2["references"] = ["ghost-id"]
    check("reference to an unknown id changes nothing", names(np_.category_ports(cat("C", a, caller2))) == ["res"])

    g = var_node("gen", ("text", "'a'"), ("extra", "1"))
    s = var_node("show", ("shown", "text"))
    s["data_uses"] = [{"id": "gen", "vars": ["text"]}]
    check("variable read inside: only THAT variable's port is hidden",
          names(np_.category_ports(cat("C", g, s))) == ["extra", "shown"])
    s2 = var_node("show", ("shown", "text")); s2["data_uses"] = [{"id": "gen", "vars": ["text", "extra"]}]
    check("all variables read: only the reader's own variable is left", names(np_.category_ports(cat("C", g, s2))) == ["shown"])
    s3 = copy.deepcopy(s); s3["data_uses"] = [{"id": "elsewhere", "vars": ["text"]}]
    check("data use of a node outside the category does not hide the port",
          names(np_.category_ports(cat("C", g, s3))) == ["text", "extra", "shown"])
    gself = var_node("gen", ("text", "1")); gself["data_uses"] = [{"id": "gen", "vars": ["text"]}]
    check("a node reading its own variable does not hide it", names(np_.category_ports(cat("C", gself))) == ["text"])
    check("function node's port is not hidden by a same-named variable read",
          names(np_.category_ports(cat("C", fn("a", "", "text"), s))) == ["text", "shown"])

    sk = fn("caller", "", "done"); sk["references"] = ["a"]; sk["skipped"] = True
    check("a SKIPPED caller does not hide the port (and has none itself)", names(np_.category_ports(cat("C", a, sk))) == ["res"])
    ig = fn("caller", "", "done"); ig["references"] = ["a"]; ig["ignored"] = True
    check("an IGNORED caller does not hide the port", names(np_.category_ports(cat("C", a, ig))) == ["res"])
    sk2 = fn("a", "x", "res"); sk2["skipped"] = True
    check("skipped/ignored nodes have no ports of their own", np_.category_ports(cat("C", sk2)) == [])

    deep = cat("Outer", fn("top", "", "t"), cat("Inner", fn("low", "", "l")))
    check("nested categories: ports from any depth, tree order", names(np_.category_ports(deep)) == ["t", "l"])
    cls = make_node("K", node_id="K", kind="class", child_nodes=[fn("m", "", "mm")])
    check("a class node's methods count", names(np_.category_ports(cat("C", cls))) == ["mm"])
    inner_cat = cat("Inner", fn("low", "", "l"))
    check("the inner category's OWN ports are those of its own children only",
          names(np_.category_ports(inner_cat)) == ["l"])

    d1, d2 = fn("one", "", "ok"), fn("two", "", "ok")
    p = np_.category_ports(cat("C", d1, d2))
    check("same port name twice: labelled with the node name", names(p) == ["one.ok", "two.ok"] and [x["name"] for x in p] == ["ok", "ok"])
    check("unique names stay plain", names(np_.category_ports(cat("C", d1, fn("two", "", "other")))) == ["ok", "other"])
    check("one-of-two duplicates after hiding one: plain again",
          names(np_.category_ports(cat("C", d1, dict(fn("two", "", "ok"), references=[])))) == ["one.ok", "two.ok"])
    hidden_two = fn("user", "", "z"); hidden_two["references"] = ["two"]
    check("a hidden duplicate no longer forces long labels",
          names(np_.category_ports(cat("C", d1, d2, hidden_two))) == ["ok", "z"])

    man = fn("a", "x", "res"); np_.set_port_color(man, "out", "res", "#112233")
    cp = np_.category_ports(cat("C", man))[0]
    check("manual colour of the inner node shows on the category port", cp["color"] == "#112233" and cp["manual"] is True)
    check("auto colour = same as on the node itself",
          np_.category_ports(cat("C", a))[0]["color"] == np_.node_ports(a)[1]["color"])
    two_same_colour = np_.category_ports(cat("C", fn("a", "", "u, v")))
    check("ports of one node keep their distinct colours", len({x["color"] for x in two_same_colour}) == 2)

    snapshot = copy.deepcopy(cat("C", a, caller, g, s))
    work = copy.deepcopy(snapshot); np_.category_ports(work)
    check("category_ports changes nothing", work == snapshot)
    junk = cat("J", None, {"kind": "function"}, {"kind": "function", "blocks": [None, ("func_def", None)], "references": None, "data_uses": [None, {"id": 1}]},
               {"kind": "category", "child_nodes": None})
    try:
        out = np_.category_ports(junk)
        check("junk children do not crash", isinstance(out, list))
    except Exception as exc:
        check(f"junk children do not crash ({exc!r})", False)
    check("category's own blocks are ignored",
          np_.category_ports(dict(cat("C"), blocks=[("assign_variable", {"variable": "z", "value": "1"})])) == [])

    # ---------------- UI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    gen = var_node("gen_pw", ("text", "'abc'"), ("extra", "1"))
    show = make_node("show_pw", node_id="show_pw", blocks=[("print_output", {"value": "text"})])
    verify = fn("verify", "password", "approved")
    helper = fn("helper", "", "approved")                        # same output name as verify
    main_n = make_node("main_n", node_id="main_n", blocks=[("print_output", {"value": "'hi'"})])
    category = cat("Utils", gen, show, verify)
    category["canvas_x"], category["canvas_y"] = 40, 60
    main_n["canvas_x"], main_n["canvas_y"] = 700, 80
    for n in (gen, show, verify): n["canvas_x"] = n["canvas_y"] = 0
    tab["nodes"] = [category, main_n]; normalize_orders(tab["nodes"])
    tab["file_view_path"] = []; tab["active_node_id"] = "main_n"
    app.active_tab_index = 0; app.view_mode = "file"
    app.refresh_workspace(); app.update(); app.update_idletasks()

    colours = {c.lower() for _n, c in np_.PORT_COLORS}
    def rows(box):
        out = []
        def walk(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Label) and str(ch.cget("text")) == "●" and str(ch.cget("fg")).lower() in colours:
                    label = [str(x.cget("text")) for x in ch.master.winfo_children() if x is not ch]
                    out.append((label[0] if label else None, ch))
                walk(ch)
        walk(box)
        return out

    box = app._fileview_boxes["Utils"][1]
    got = rows(box)
    check("category box shows the unused inner outputs (text hidden: show_pw reads it)",
          sorted(n for n, _d in got) == ["approved", "extra"])
    check("inner nodes of a category are not drawn at this level", "gen_pw" not in app._fileview_boxes)
    check("data wire inside the category is derived (gen_pw -> show_pw)",
          find_node_by_id(tab["nodes"], "show_pw")["data_uses"] == [{"id": "gen_pw", "vars": ["text"]}])
    check("the plain node box is unaffected (no ports)", rows(app._fileview_boxes["main_n"][1]) == [])

    def press_dot(dot, rootx=None, rooty=None):
        dot.update_idletasks()
        x = dot.winfo_rootx() + dot.winfo_width() // 2 if rootx is None else rootx
        y = dot.winfo_rooty() + dot.winfo_height() // 2 if rooty is None else rooty
        dot.event_generate("<ButtonPress-1>", rootx=x, rooty=y, x=1, y=1)
        return x, y
    def ev(x, y): return types.SimpleNamespace(x_root=x, y_root=y, widget=None)
    def drop_xy(node_id):
        w = app._fileview_boxes[node_id][1]
        return w.winfo_rootx() + w.winfo_width() // 2, w.winfo_rooty() + w.winfo_height() - 6

    # drag the function port 'approved' (owner verify) onto main_n
    dot = dict(got)["approved"]
    press_dot(dot)
    check("press on a category port starts a drag from the CATEGORY box", app._wire_drag_source == "Utils")
    check("...whose real source is the inner node", app._wire_drag_owner == "verify")
    tx, ty = drop_xy("main_n"); app._port_motion(ev(tx, ty)); app._port_release(ev(tx, ty)); app.update()
    blocks = main_n["blocks"]
    check("target got the inner node's call 'approved = verify(password)'",
          len(blocks) == 2 and blocks[1][0] == "assign_variable" and blocks[1][1]["variable"] == "approved"
          and blocks[1][1]["value"]["_nested_params"] == {"name": "verify", "args": "password"})
    check("drag state cleaned up", app._wire_drag_source is None and app._wire_drag_owner is None)
    check("the category's inner nodes are untouched", len(verify["blocks"]) == 1 and len(category["blocks"]) == 0)
    check("use from OUTSIDE does not hide the port",
          sorted(n for n, _d in rows(app._fileview_boxes["Utils"][1])) == ["approved", "extra"])

    # variable port 'extra' (owner gen_pw): lands as a print in main_n
    dot = dict(rows(app._fileview_boxes["Utils"][1]))["extra"]
    press_dot(dot); tx, ty = drop_xy("main_n"); app._port_motion(ev(tx, ty)); app._port_release(ev(tx, ty)); app.update()
    check("variable port from a category: target prints it",
          main_n["blocks"][-1] == ("print_output", {"value": "extra"}))

    # a plain click on a port opens the colour menu of the INNER node
    seen = []
    app._popup = lambda menu, e: seen.append(menu)
    dot = dict(rows(app._fileview_boxes["Utils"][1]))["approved"]
    x, y = press_dot(dot)
    app._port_release(ev(x, y)); app.update()
    check("click (no drag) opens one colour menu", len(seen) == 1)
    seen[0].invoke(0); app.update()                       # first entry of the menu = Blue
    check("colour picked in that menu lands on the INNER node", verify.get("port_colors") == {"out:approved": "#4f8fd6"})
    check("...and shown on the category's port",
          str(dict(rows(app._fileview_boxes["Utils"][1]))["approved"].cget("fg")).lower() == "#4f8fd6")
    check("the category itself stores no colours", "port_colors" not in category)

    # releasing on empty canvas cancels
    n_before = len(main_n["blocks"])
    dot = dict(rows(app._fileview_boxes["Utils"][1]))["extra"]
    press_dot(dot); app._port_motion(ev(300, 700)); app._port_release(ev(300, 700)); app.update()
    check("drop on empty canvas: nothing added", len(main_n["blocks"]) == n_before and app._wire_drag_owner is None)

    # editing inside the category changes the ports (derived)
    show["blocks"].append(("func_call", {"name": "verify", "args": "'x'"}))
    app.refresh_workspace(); app.update()
    check("an inner node now calls verify: its 'approved' port is gone",
          sorted(n for n, _d in rows(app._fileview_boxes["Utils"][1])) == ["extra"])
    show["ignored"] = True; app.refresh_workspace(); app.update()
    check("ignoring the caller brings the port back",
          sorted(n for n, _d in rows(app._fileview_boxes["Utils"][1])) == ["approved", "extra", "text"])
    del show["ignored"]
    show["blocks"].pop()                                   # show no longer calls verify
    category["child_nodes"].append(helper); helper["canvas_x"] = helper["canvas_y"] = 0
    app.refresh_workspace(); app.update()
    check("two 'approved' outputs: labelled with their nodes",
          sorted(n for n, _d in rows(app._fileview_boxes["Utils"][1])) == ["extra", "helper.approved", "verify.approved"])

    # nothing about ports is saved except manual colours on real nodes
    saved = json.dumps(project_file.build_project_data("python", tab["nodes"], "main_n"))
    check("saved file has no derived category ports", "category_ports" not in saved and '"src"' not in saved)

    # zoomed far out: compact boxes draw without ports and without errors
    app.set_zoom(0.3); app.update(); app.update_idletasks()
    check("compact zoom: category box still drawn, no port dots", "Utils" in app._fileview_boxes
          and rows(app._fileview_boxes["Utils"][1]) == [])
    app.set_zoom(1.0); app.update()
    check("zoom back: ports are back", len(rows(app._fileview_boxes["Utils"][1])) == 3)

    # inside the category the inner nodes show their own ports as before
    app.open_node("Utils"); app.update()
    check("open category: inner nodes drawn, function node keeps its own ports",
          "verify" in app._fileview_boxes and any(n == "approved" for n, _d in rows(app._fileview_boxes["verify"][1])))
    app.destroy()
    print("FAILURES:", len(FAILURES))
    sys.exit(1 if FAILURES else 0)

main()
