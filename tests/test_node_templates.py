"""Node templates: format, folders, saving, variables, instantiate, and the
UI (save dialog, add from menus, variable dialog). Run under Xvfb."""
import os, sys, json, tempfile, shutil, itertools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import node_templates as N
from nodes_model import make_node, function_nodes_in_tree_order, find_node_by_id

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def ids():
    c = itertools.count(1)
    return lambda: f"id{next(c)}"

def tpl(**kw):
    t = {"format": N.FORMAT, "version": 1, "name": "T", "kind": "function", "blocks": [], "variables": []}
    t.update(kw); return t

def pure():
    # ---- scanning
    n = make_node("Login {{svc}}", node_id="a", blocks=[("x", {"p": "{{user}} and {{ user }}", "_children": [("y", {"q": ["{{deep}}", {"k": "{{svc}}"}]})]}),
                                                     ("z", {"bad": "{{1x}} {{a b}} { {c} }"})])
    check("scan: names in name, params, nested, lists; unique; first-use order; ignores invalid", N.scan_variables(n) == ["svc", "user", "deep"])
    cls = make_node("C{{k}}", node_id="c", kind="class", child_nodes=[make_node("m", node_id="m", blocks=[("x", {"p": "{{inner}}"})])])
    check("scan: class children included", N.scan_variables(cls) == ["k", "inner"])
    check("scan: caps at MAX_VARIABLES", len(N.scan_variables(make_node("n", blocks=[("x", {"p": " ".join("{{v%d}}" % i for i in range(50))})]))) == N.MAX_VARIABLES)

    # ---- build
    live = make_node("Login {{svc}}", node_id="zz", blocks=[("assign_variable", {"variable": "u", "value": "{{user}}"})], locked=True, node_type_id="start", order=3)
    live["canvas_x"], live["canvas_y"], live["references"] = 5, 6, ["q"]
    t = N.build_template(live, description="  hi  ", defaults={"svc": "API"})
    check("build: keeps name/kind/blocks/description", t["name"] == "Login {{svc}}" and t["kind"] == "function" and t["description"] == "hi" and t["blocks"] == [["assign_variable", {"variable": "u", "value": "{{user}}"}]])
    check("build: variables with defaults, label from name", t["variables"] == [{"name": "svc", "label": "Svc", "default": "API"}, {"name": "user", "label": "User", "default": ""}])
    check("build: strips id/position/order/lock/references", not ({"id", "canvas_x", "canvas_y", "order", "locked", "references", "node_type_id"} & set(t)))
    check("build: blank name falls back to node name", N.build_template(live, name="   ")["name"] == "Login {{svc}}")
    ct = N.build_template(cls)
    check("build: class keeps children (no ids)", ct["kind"] == "class" and ct["child_nodes"][0]["name"] == "m" and "id" not in ct["child_nodes"][0] and "blocks" not in ct)
    try: N.build_template(make_node("cat", kind="category")); ok = False
    except ValueError: ok = True
    check("build: category refused", ok)
    check("build: does not alias the live blocks", t["blocks"] is not live["blocks"] and t["blocks"][0][1] is not live["blocks"][0][1])

    # ---- parse
    back, notes = N.parse_template(json.loads(json.dumps(t)))
    check("parse: round trip gives tuples again", back["blocks"] == [("assign_variable", {"variable": "u", "value": "{{user}}"})] and isinstance(back["blocks"][0], tuple) and notes == [])
    for label, bad in (("string", "x"), ("list", []), ("other format", {"format": "nope", "name": "a"}), ("no name", {"kind": "function"}),
                       ("blank name", {"name": "  "}), ("bad kind", {"name": "a", "kind": "category"}), ("number name", {"name": 5})):
        r, nn = N.parse_template(bad)
        check(f"parse rejects: {label}", r is None and nn)
    r, nn = N.parse_template({"name": "a", "variables": ["plain", {"name": "plain"}, {"name": "ok", "label": " ", "default": 5}, {"name": "1bad"}, 7, {"name": "ok"}], "blocks": [["x", {}], "junk"]})
    check("parse: variables sanitized (string form ok, dups/bad names dropped, bad label/default fixed)", [v["name"] for v in r["variables"]] == ["plain", "ok"] and r["variables"][1]["label"] == "ok" and r["variables"][1]["default"] == "")
    check("parse: damaged block dropped with a note", r["blocks"] == [("x", {})] and nn)
    deep = {"name": "c0", "kind": "class", "child_nodes": []}
    cur = deep
    for i in range(12):
        nxt = {"name": f"c{i+1}", "kind": "class", "child_nodes": []}; cur["child_nodes"].append(nxt); cur = nxt
    r, nn = N.parse_template(deep)
    d, cur = 0, r
    while cur["child_nodes"]: cur = cur["child_nodes"][0]; d += 1
    check("parse: absurd nesting is cut off", d < 12 and nn)

    # ---- folders
    tmp = tempfile.mkdtemp()
    def put(rel, data, raw=False):
        p = os.path.join(tmp, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(data if raw else json.dumps(data))
    put("general/prebuilt/g.json", tpl(name="Gen"))
    put("python/custom/b.json", tpl(name="beta"))
    put("python/custom/a.json", tpl(name="Alpha"))
    put("python/prebuilt/p.json", tpl(name="Pre"))
    put("rust/custom/r.json", tpl(name="RustOnly"))
    put("python/custom/broken.json", "{nope", raw=True)
    put("python/custom/notatemplate.json", {"hello": 1})
    put("python/custom/readme.txt", "hi", raw=True)
    put("python/custom/.hidden.json", tpl(name="Hidden"))
    put("python/other/x.json", tpl(name="WrongFolder"))
    e, notes = N.load_folder(tmp, "python")
    names = [x["template"]["name"] for x in e]
    check("load: python sees general + python, sorted case-insensitively", names == ["Alpha", "beta", "Gen", "Pre"])
    check("load: other languages' folders, bad folders, txt and dotfiles ignored", "RustOnly" not in names and "WrongFolder" not in names and "Hidden" not in names)
    check("load: damaged and non-template files are reported, not fatal", len(notes) == 2 and any("broken.json" in x for x in notes) and any("notatemplate.json" in x for x in notes))
    check("load: entries know their folder kind and scope", {(x["template"]["name"], x["folder_kind"], x["scope"]) for x in e} >= {("Gen", "prebuilt", "general"), ("Alpha", "custom", "python")})
    check("load: unsafe language names load nothing", all(N.load_folder(tmp, bad) == ([], []) for bad in ("../x", "Py", "", "a/b", None)))
    check("load: missing root is fine", N.load_folder(os.path.join(tmp, "nope"), "python") == ([], []))
    e2, _ = N.load_all([tmp, tmp, os.path.join(tmp, "..", os.path.basename(tmp))], "python")
    check("load_all: the same real folder is only read once", len(e2) == 4)

    # ---- save
    root = tempfile.mkdtemp()
    p1 = N.save_custom(root, "python", tpl(name="My Login!"))
    p2 = N.save_custom(root, "python", tpl(name="My Login!"))
    check("save: slugged file in <scope>/custom, never overwrites", p1.endswith(os.path.join("python", "custom", "my_login.json")) and p2.endswith("my_login_2.json") and os.path.exists(p1) and os.path.exists(p2))
    check("save: no temp file left behind", not [f for f in os.listdir(os.path.dirname(p1)) if f.endswith(".tmp")])
    check("save: weird names still give a file name", N.save_custom(root, "general", tpl(name="***")).endswith("node.json"))
    for bad in ("../x", "Py", "", "a/b", "..", None):
        try: N.save_custom(root, bad, tpl()); ok = False
        except ValueError: ok = True
        check(f"save: scope {bad!r} refused", ok)
    check("save: nothing escaped the root", sorted(os.listdir(root)) == ["general", "python"] and os.path.exists(os.path.join(os.path.dirname(root), "x")) is False)
    check("save: result is loadable again", [x["template"]["name"] for x in N.load_folder(root, "python")[0] if x["scope"] == "python"] == ["My Login!", "My Login!"])

    # ---- instantiate
    known = {"assign_variable", "if_statement", "print_output"}
    t = N.parse_template({"name": "Login {{svc}}", "description": "", "variables": [{"name": "svc", "default": "API"}, {"name": "user", "default": "me"}],
                          "blocks": [["assign_variable", {"variable": "u", "value": "{{user}}@{{svc}}"}],
                                     ["if_statement", {"condition": "True", "_children": [["print_output", {"value": "{{user}}"}]]}],
                                     ["print_output", {"value": "{{undeclared}} {{svc}}"}]]})[0]
    node, notes = N.instantiate(t, {"user": "bob"}, known, "raw_code", "code", ids())
    check("inst: name + params + nested substituted, default used when not given", node["name"] == "Login API" and node["blocks"][0][1]["value"] == "bob@API" and node["blocks"][1][1]["_children"][0][1]["value"] == "bob")
    check("inst: undeclared {{x}} left literal", node["blocks"][2][1]["value"] == "{{undeclared}} API")
    node2, _ = N.instantiate(t, {"user": "x", "ghost": "boo"}, known, "raw_code", "code", ids())
    check("inst: values for unknown variables are ignored; template not mutated", node2["blocks"][0][1]["value"] == "x@API" and t["blocks"][0][1]["value"] == "{{user}}@{{svc}}")
    node3, _ = N.instantiate(t, {"user": "{{svc}}"}, known, "raw_code", "code", ids())
    check("inst: a value that looks like {{x}} is not substituted again", node3["blocks"][0][1]["value"] == "{{svc}}@API")
    node4, notes = N.instantiate(t, {}, {"print_output"}, "raw_code", "code", ids())
    check("inst: unknown blocks skipped with notes (also nested), the rest kept", [b[0] for b in node4["blocks"]] == ["print_output"] and len(notes) >= 2 and all("not available" in x for x in notes))
    rt = N.parse_template({"name": "R", "variables": [{"name": "v", "default": "1"}], "blocks": [["@raw", {"code": "a = {{v}}\n\n    b = 2\n"}]]})[0]
    node, _ = N.instantiate(rt, {}, set(), "raw_code", "code", ids())
    check("inst: @raw -> one raw block per line, blank lines kept, one trailing newline dropped", node["blocks"] == [("raw_code", {"code": "a = 1"}), ("raw_code", {"code": ""}), ("raw_code", {"code": "    b = 2"})])
    node, notes = N.instantiate(rt, {}, set(), None, None, ids())
    check("inst: @raw with no raw block in the language -> skipped + note", node["blocks"] == [] and any("raw" in x for x in notes))
    ct = N.parse_template({"name": "K{{v}}", "kind": "class", "variables": [{"name": "v", "default": "1"}], "child_nodes": [{"name": "m", "blocks": [["print_output", {"value": "{{v}}"}]]}, {"name": "m2", "blocks": []}]})[0]
    node, _ = N.instantiate(ct, {}, known, "raw_code", "code", ids())
    allids = [node["id"]] + [c["id"] for c in node["child_nodes"]]
    check("inst: class + children, fresh unique ids, no lock/refs", node["kind"] == "class" and node["name"] == "K1" and len(set(allids)) == 3 and node["child_nodes"][0]["blocks"][0][1]["value"] == "1" and not node["locked"])

def ui():
    from ui import BlocklinerUI
    import ui_codegen, ui_nodetemplates
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    app.save_app_settings = lambda: None
    infos, errors = [], []
    for mod in (ui_codegen, ui_nodetemplates):
        mod.messagebox.showinfo = lambda *a, **k: infos.append(a)
        mod.messagebox.showerror = lambda *a, **k: errors.append(a)
        mod.messagebox.showwarning = lambda *a, **k: errors.append(a)
    app.maybe_notify = lambda *a, **k: None
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nodes")
    user = tempfile.mkdtemp()
    app.node_template_roots = lambda: [bundled, user]
    app.node_template_save_root = lambda: user
    tab = app.tabs[app.active_tab_index]
    src = function_nodes_in_tree_order(tab["nodes"])[0]
    src["blocks"] = [("assign_variable", {"variable": "{{who}}", "value": "1"})]
    app.project_blocks = src["blocks"]; app.goto_layer("nodes"); app.update()

    # ---- shipped templates generate real, compilable code
    entries = app.available_node_templates()
    shipped = {e["template"]["name"]: e for e in entries}
    check("shipped: python prebuilt + general prebuilt are found", {"Command-line input loop", "Read JSON file", "HTTP GET request", "Header comment"} <= set(shipped))
    app.ask_template_variables = lambda t: {v["name"]: v["default"] for v in t["variables"]}
    for name, e in shipped.items():
        before = len(app.get_current_node_list(tab))
        node = app.insert_node_template(e, (300, 200))
        code = app.generate_code_for_node(node, "python")
        try:
            compile(code, name, "exec"); ok = True
        except SyntaxError as ex:
            ok = False; print("   ", name, ex, repr(code))
        check(f"shipped '{name}': compiles, no {{{{ left, added once", ok and "{{" not in code and len(app.get_current_node_list(tab)) == before + 1)
    cli = app.generate_code_for_node(next(n for n in function_nodes_in_tree_order(tab["nodes"]) if n["name"] == "Command-line input loop"), "python")
    check("shipped: variable values really land in the code", 'input("> ")' in cli and '!= "quit"' in cli)
    check("shipped: no popups for clean templates", not infos and not errors)

    # ---- variables dialog (real Toplevel)
    t = shipped["HTTP GET request"]["template"]
    del app.ask_template_variables
    def fill_and_click(button_text, values=None):
        top = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        rows = [w for w in top.winfo_children() if isinstance(w, tk.Frame) and any(isinstance(c, tk.Entry) for c in w.winfo_children())]
        for row, v in zip(rows, values or []):
            e = next(c for c in row.winfo_children() if isinstance(c, tk.Entry)); e.delete(0, "end"); e.insert(0, v)
        for f in top.winfo_children():
            for b in ([f] + list(f.winfo_children())):
                if isinstance(b, tk.Button) and b.cget("text") == button_text: b.invoke(); return
    app.after(150, lambda: fill_and_click("Add node", ["http://x.test", "body"]))
    got = app.ask_template_variables(t)
    check("dialog: returns what was typed, keyed by variable", got == {"url": "http://x.test", "result": "body"})
    app.after(150, lambda: fill_and_click("Add node"))
    check("dialog: untouched boxes give the defaults", app.ask_template_variables(t) == {"url": "https://example.com", "result": "response_text"})
    app.after(150, lambda: fill_and_click("Cancel"))
    check("dialog: Cancel returns None", app.ask_template_variables(t) is None)
    def press_escape():
        top = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        top.focus_force(); top.update()
        top.event_generate("<Escape>")
        app.after(800, lambda: top.winfo_exists() and top.destroy())      # failsafe: fail, don't hang
    app.after(150, press_escape)
    esc_result = app.ask_template_variables(t)
    check("dialog: Escape returns None", esc_result is None)
    n_before = len(app.get_current_node_list(tab))
    app.after(150, lambda: fill_and_click("Cancel"))
    check("cancelled dialog adds nothing", app.insert_node_template(shipped["HTTP GET request"], (1, 1)) is None and len(app.get_current_node_list(tab)) == n_before)

    # ---- insert behaviour
    app.ask_template_variables = lambda t: {v["name"]: v["default"] for v in t["variables"]}
    app.refresh_workspace()
    wires = len(src["blocks"])
    node = app.insert_node_template(shipped["Read JSON file"], (123, 45), wire_from=src["id"])
    check("insert: at the drop position, wired from the source, marked dirty", (node["canvas_x"], node["canvas_y"]) == (123, 45) and len(src["blocks"]) == wires + 1 and src["blocks"][-1][1]["name"] == node["name"] and tab["dirty"])
    check("insert: gets an execution order", isinstance(node.get("order"), int))
    node_b = app.insert_node_template(shipped["Read JSON file"], (10, 10))
    fn_names = [n["name"] for n in function_nodes_in_tree_order(tab["nodes"])]
    check("insert: copies get unique names (wires resolve by name), same base", len(set(fn_names)) == len(fn_names) and node_b["name"] != node["name"] and node_b["name"].startswith("Read JSON file") and node_b["id"] != node["id"])
    check("insert: without wire_from nothing is wired", len(src["blocks"]) == wires + 1)
    unknown = {"template": N.parse_template({"name": "Odd", "blocks": [["no_such_block", {}], ["print_output", {"value": "1"}]]})[0], "folder_kind": "custom", "scope": "python", "path": ""}
    infos.clear()
    node_c = app.insert_node_template(unknown, (1, 1))
    check("insert: unknown block skipped, node still added, user told", [b[0] for b in node_c["blocks"]] == ["print_output"] and len(infos) == 1 and "no_such_block" in infos[0][1])

    # ---- save as template
    live = make_node("Auth {{svc}}", node_id="authnode", blocks=[("assign_variable", {"variable": "tok", "value": "\"{{svc}}\""})])
    tab["nodes"].append(live)
    path = app.save_node_as_template("authnode", name="Auth flow", description="d", defaults={"svc": "GitHub"})
    check("save: file lands in <user>/python/custom", os.path.dirname(path) == os.path.join(user, "python", "custom") and os.path.exists(path))
    saved = json.load(open(path))
    check("save: file has variables + defaults, no ids/positions", saved["variables"] == [{"name": "svc", "label": "Svc", "default": "GitHub"}] and "id" not in saved and "canvas_x" not in saved)
    custom = [e for e in app.available_node_templates() if e["folder_kind"] == "custom"]
    check("save: shows up as a custom template right away", [e["template"]["name"] for e in custom] == ["Auth flow"])
    gp = app.save_node_as_template("authnode", scope="general")
    check("save: general scope goes to <user>/general/custom", os.path.dirname(gp) == os.path.join(user, "general", "custom"))
    for bad in ("../evil", "X Y"):
        try: app.save_node_as_template("authnode", scope=bad); ok = False
        except ValueError: ok = True
        check(f"save: bad scope {bad!r} refused", ok)
    try: app.save_node_as_template("nope"); ok = False
    except ValueError: ok = True
    check("save: unknown node id refused", ok)
    back = app.insert_node_template(custom[0], (5, 5))
    check("round trip: adding the saved template reproduces the node with the default", back["blocks"] == [("assign_variable", {"variable": "tok", "value": "\"GitHub\""})] and back["name"] == "Auth flow")

    # ---- save dialog (real Toplevel)
    def drive_save(name):
        top = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        entries = [w for w in top.winfo_children() if isinstance(w, tk.Entry)]
        entries[0].delete(0, "end"); entries[0].insert(0, name)
        for b in top.winfo_children():
            for x in ([b] + list(b.winfo_children())):
                if isinstance(x, tk.Button) and x.cget("text") == "Save template": x.invoke(); return
    import time
    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.update(); time.sleep(0.02)
    app.save_node_as_template_dialog("authnode")
    app.update(); drive_save("From dialog"); pump(0.3)
    check("save dialog: saves under the typed name and closes", os.path.exists(os.path.join(user, "python", "custom", "from_dialog.json")) and not [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)])
    files_before = sorted(os.listdir(os.path.join(user, "python", "custom")))
    errors.clear()
    app.save_node_as_template_dialog("authnode")
    app.update(); drive_save("   "); pump(0.3)
    open_dialogs = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    check("save dialog: blank name warns, saves nothing, stays open", len(errors) == 1 and sorted(os.listdir(os.path.join(user, "python", "custom"))) == files_before and len(open_dialogs) == 1)
    for w in open_dialogs: w.destroy()

    # ---- menus
    app.goto_layer("nodes"); app.update()
    def labels(menu): return [(menu.type(i), menu.entrycget(i, "label")) for i in range(menu.index("end") + 1) if menu.type(i) in ("command", "cascade")]
    def sub(menu, label):
        for i in range(menu.index("end") + 1):
            if menu.type(i) == "cascade" and menu.entrycget(i, "label") == label:
                return app.nametowidget(menu.entrycget(i, "menu"))
    dm = app.build_drop_menu(src["id"], (50, 60))
    check("drop menu: starters first, then Custom/Prebuilt cascades", [l for t_, l in labels(dm)][-2:] == ["Custom nodes", "Prebuilt nodes"] and labels(dm)[0][1].endswith("New node"))
    pre = [l for t_, l in labels(sub(dm, "Prebuilt nodes"))]
    check("drop menu: prebuilt list has python modules and the general one (tagged)", "Read JSON file" in pre and "Header comment  (all languages)" in pre)
    check("drop menu: custom list has the saved one", "Auth flow" in [l for t_, l in labels(sub(dm, "Custom nodes"))])
    wires = len(src["blocks"]); nn = len(app.get_current_node_list(tab))
    cm = sub(dm, "Custom nodes")
    for i in range(cm.index("end") + 1):
        if cm.entrycget(i, "label") == "Auth flow": cm.invoke(i); break
    check("drop menu: picking a template adds it at the drop point, wired", len(app.get_current_node_list(tab)) == nn + 1 and len(src["blocks"]) == wires + 1 and app.get_current_node_list(tab)[-1]["canvas_x"] == 50)
    wm = app.build_workspace_menu((70, 80))
    check("Nodes right-click menu has the template cascades", sub(wm, "Prebuilt nodes") is not None and sub(wm, "Custom nodes") is not None)
    wires = len(src["blocks"]); nn = len(app.get_current_node_list(tab))
    pm = sub(wm, "Prebuilt nodes")
    for i in range(pm.index("end") + 1):
        if pm.entrycget(i, "label") == "Read JSON file": pm.invoke(i); break
    check("Nodes right-click: adds the node without a wire", len(app.get_current_node_list(tab)) == nn + 1 and len(src["blocks"]) == wires)
    empty_root = tempfile.mkdtemp(); app.node_template_roots = lambda: [empty_root]
    check("no templates: no cascades at all", sub(app.build_drop_menu(src["id"], (0, 0)), "Custom nodes") is None and sub(app.build_workspace_menu((0, 0)), "Prebuilt nodes") is None)
    app.node_template_roots = lambda: [bundled, user]
    app.goto_layer("files"); app.update()
    check("Files-layer menu has no template cascades", sub(app.build_workspace_menu((0, 0)), "Prebuilt nodes") is None)
    app.goto_layer("nodes"); app.update()
    nm = app.build_node_menu(src["id"])
    check("node menu: Save as node template for a function node", any(l.startswith("Save as node template") for t_, l in labels(nm)))
    cat = make_node("cat", node_id="catid", kind="category"); tab["nodes"].append(cat)
    cls = make_node("cls", node_id="clsid", kind="class", child_nodes=[]); tab["nodes"].append(cls)
    check("node menu: offered for class, not for category", any(l.startswith("Save as node template") for t_, l in labels(app.build_node_menu("clsid"))) and not any(l.startswith("Save as node template") for t_, l in labels(app.build_node_menu("catid"))))
    check("no unexpected error popups", not [e for e in errors[1:]])
    app.destroy()
    shutil.rmtree(user, ignore_errors=True)

if __name__ == "__main__":
    pure(); ui()
    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)
