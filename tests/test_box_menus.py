"""Node-box and file-box right-click menus + the operations behind them
(rename with reference rewriting, delete with orphan count, move to
category, close file). Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import BlocklinerUI, make_node, default_active_node_id, find_node_by_id

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def entries(menu):
    out = []
    end = menu.index("end")
    if end is None: return out
    for i in range(end + 1):
        t = menu.type(i)
        out.append(("-", None) if t == "separator" else (menu.entrycget(i, "label"), str(menu.entrycget(i, "state"))))
    return out

def call(name, args=""):
    return ("func_call", {"name": name, "args": args})

def calls_named(app, tab, name):
    n = 0
    with app._language_scope(tab["language"]):
        for fn in app.all_function_nodes(tab):
            for bid, p in app.iter_all_blocks_recursive(fn["blocks"]):
                if bid == "func_call" and (p.get("name") or "").strip() == name:
                    n += 1
    return n

def setup_nodes(app):
    tab = app.tabs[0]
    alpha = make_node("Alpha", node_id="a1", blocks=[call("Beta")])
    beta = make_node("Beta", node_id="b1", blocks=[])
    chip = {"_nested_block": "func_call", "_nested_params": {"name": "Beta", "args": ""}}
    gamma = make_node("Gamma", node_id="g1", blocks=[
        ("if_statement", {"condition": "x", "_children": [call(" Beta ")]}),
        ("assign_variable", {"variable": "v", "value": chip}),
        call("Other"),
    ])
    delta = make_node("Delta", node_id="d1", blocks=[call("Beta")])
    folder = make_node("Folder", node_id="f1", kind="category", child_nodes=[delta])
    tab["nodes"] = [alpha, beta, gamma, folder]
    tab["active_node_id"] = alpha["id"]
    tab["file_view_path"] = []
    app.project_blocks = alpha["blocks"]
    return tab, alpha, beta, gamma, folder, delta, chip

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()

    asked = []; warned = []
    real = (ui.simpledialog.askstring, ui.messagebox.askyesno, ui.messagebox.showwarning)
    ui.messagebox.showwarning = lambda title, msg, **k: warned.append(msg)
    def stub_ask(answer):
        ui.simpledialog.askstring = lambda *a, **k: answer
    def stub_yes(answer):
        def f(title, msg, **k): asked.append(msg); return answer
        ui.messagebox.askyesno = f

    try:
        # ================= RENAME NODE =================
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        app.refresh_workspace()
        check("wires resolved before rename", beta["id"] in alpha["references"])
        ok, msg, n = app.rename_node(tab, beta, "Omega")
        check("rename succeeds", ok and beta["name"] == "Omega")
        check("rewrote plain, container-nested (with spaces), chip and category-nested calls (4)", n == 4)
        check("no call to the old name is left", calls_named(app, tab, "Beta") == 0)
        check("all calls now point at Omega", calls_named(app, tab, "Omega") == 4)
        check("chip call was rewritten in place", chip["_nested_params"]["name"] == "Omega")
        check("unrelated call 'Other' untouched", calls_named(app, tab, "Other") == 1)
        check("wires survive the rename",
              beta["id"] in alpha["references"] and beta["id"] in delta["references"]
              and beta["id"] in gamma["references"])
        check("tab marked dirty", tab["dirty"] is True)

        ok, msg, n = app.rename_node(tab, beta, "")
        check("empty name refused", not ok and "empty" in msg.lower())
        ok, msg, n = app.rename_node(tab, beta, "Alpha")
        check("duplicate name refused (would rewire)", not ok and "already" in msg and beta["name"] == "Omega")
        ok, msg, n = app.rename_node(tab, beta, "Delta")
        check("duplicate of a NESTED node refused too", not ok)
        ok, msg, n = app.rename_node(tab, beta, "Omega")
        check("same name is a harmless no-op", ok and n == 0)
        ok, msg, n = app.rename_node(tab, folder, "Stuff")
        check("categories rename without touching calls", ok and folder["name"] == "Stuff" and n == 0)
        ok, msg, n = app.rename_node(tab, folder, "Omega")
        check("category can't take a function's name", not ok)
        locked = make_node("main", node_id="L1", blocks=[], locked=True)
        tab["nodes"].append(locked)
        ok, msg, n = app.rename_node(tab, locked, "x")
        check("locked node refuses rename", not ok and locked["name"] == "main")

        # dialog wrapper
        stub_ask("Renamed")
        app.rename_node_dialog("b1")
        check("rename dialog applies the typed name", beta["name"] == "Renamed" and calls_named(app, tab, "Renamed") == 4)
        stub_ask(None)
        app.rename_node_dialog("b1")
        check("cancelled rename dialog changes nothing", beta["name"] == "Renamed")
        stub_ask("Alpha"); warned.clear()
        app.rename_node_dialog("b1")
        check("refused rename shows a warning", len(warned) == 1 and beta["name"] == "Renamed")
        app.rename_node_dialog("nope")
        check("stale node id is a safe no-op", True)

        # ================= DELETE NODE =================
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        app.refresh_workspace()
        check("count_calls_to counts every orphaned call (alpha 1 + gamma 2 + delta 1)",
              app.count_calls_to(tab, beta) == 4)
        stub_yes(False); asked.clear()
        app.delete_node_dialog("b1")
        check("dialog mentions the orphan count", len(asked) == 1 and "4 calls" in asked[0])
        check("declining the confirm deletes nothing", find_node_by_id(tab["nodes"], "b1") is not None)
        stub_yes(True)
        app.delete_node_dialog("b1")
        check("confirmed delete removes the node", find_node_by_id(tab["nodes"], "b1") is None)
        check("calls to it stay in the code, unresolved",
              calls_named(app, tab, "Beta") == 4 and alpha["references"] == [])

        # containers and nesting
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        app.refresh_workspace()
        asked.clear(); stub_yes(True)
        app.delete_node_dialog("f1")
        check("deleting a category warns about the nodes inside", "1 node inside" in asked[0])
        check("category and its child are gone", find_node_by_id(tab["nodes"], "f1") is None
              and find_node_by_id(tab["nodes"], "d1") is None)
        check("calls from the deleted subtree don't count as orphans", "call" not in asked[0].split("inside")[1])

        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        ok, msg, n = app.delete_node(tab, delta)
        check("a node nested in a category can be deleted", ok and folder["child_nodes"] == [])

        # active node handling
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        alpha["blocks"] = [("assign_variable", {"variable": "keep", "value": "1"})]
        beta["blocks"] = [("assign_variable", {"variable": "z", "value": "9"})]
        tab["active_node_id"] = beta["id"]; app.project_blocks = beta["blocks"]
        ok, msg, n = app.delete_node(tab, beta)
        check("deleting the ACTIVE node re-points the active node", tab["active_node_id"] == "a1")
        check("project_blocks re-pointed to the new active node", app.project_blocks is alpha["blocks"])
        app.sync_active_tab_state()
        check("sync afterwards can't resurrect or overwrite anything",
              alpha["blocks"] == [("assign_variable", {"variable": "keep", "value": "1"})]
              and find_node_by_id(tab["nodes"], "b1") is None)

        # guards
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        tab["nodes"] = [alpha]
        ok, msg, n = app.delete_node(tab, alpha)
        check("the last function node can't be deleted", not ok and "at least one" in msg and tab["nodes"] == [alpha])
        tab["nodes"] = [alpha, make_node("main", node_id="L2", blocks=[], locked=True)]
        ok, msg, n = app.delete_node(tab, tab["nodes"][1])
        check("locked node can't be deleted", not ok and len(tab["nodes"]) == 2)
        cls = make_node("Program", node_id="c9", kind="class", locked=True,
                        child_nodes=[make_node("Main", node_id="m9", blocks=[], locked=True)])
        holder = make_node("Holder", node_id="h9", kind="category", child_nodes=[cls])
        tab["nodes"] = [alpha, holder]
        ok, msg, n = app.delete_node(tab, holder)
        check("a category containing a locked node can't be deleted", not ok and holder in tab["nodes"])
        warned.clear(); app.delete_node_dialog("c9")
        check("delete dialog on a locked node warns instead of asking", len(warned) == 1)

        # ================= MOVE =================
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        app.refresh_workspace()
        sub = make_node("Sub", node_id="s1", kind="category", child_nodes=[])
        folder["child_nodes"].append(sub)
        labels = [l for l, _ in app.move_destinations(tab, alpha)]
        check("top-level node can go into any category (nested shown as a path)",
              labels == ["Folder", "Folder > Sub"])
        labels = [l for l, _ in app.move_destinations(tab, delta)]
        check("a nested node can go to top level or a sibling category, not where it is",
              labels == ["Top level", "Folder > Sub"])
        labels = [l for l, _ in app.move_destinations(tab, folder)]
        check("a category can't be moved into itself or its own descendants", labels == [])
        alpha.update(canvas_x=500, canvas_y=500)
        dest = dict(app.move_destinations(tab, alpha))["Folder > Sub"]
        ok, msg, n = app.move_node(tab, alpha, dest)
        check("move puts the node in the category", ok and alpha in sub["child_nodes"] and alpha not in tab["nodes"])
        check("moved node loses its stale canvas position", "canvas_x" not in alpha or alpha["canvas_x"] != 500)
        app.refresh_workspace()
        check("wires survive a move (calls resolve by name)", beta["id"] in alpha["references"])
        dest = dict(app.move_destinations(tab, alpha))["Top level"]
        ok, msg, n = app.move_node(tab, alpha, dest)
        check("move back to top level works", ok and alpha in tab["nodes"] and alpha not in sub["child_nodes"])
        ok, msg, n = app.move_node(tab, folder, sub["child_nodes"])
        check("moving a category into its own child is refused", not ok and folder in tab["nodes"])
        ok, msg, n = app.move_node(tab, alpha, [])
        check("an arbitrary list isn't a valid destination", not ok)
        check("locked node has no destinations",
              app.move_destinations(tab, make_node("m", node_id="q", locked=True)) == [])
        names = [x["name"] for x, _p in app.iter_tab_nodes(tab)]
        check("no node duplicated or lost by moving (6 nodes, all distinct)", len(names) == 6 and len(set(names)) == 6)

        # ================= NODE MENU + BINDINGS =================
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        tab["nodes"].append(make_node("main", node_id="L3", blocks=[], locked=True))
        app.switch_to_file_view(); app.file_view_code_mode = False
        app.refresh_workspace(); app.update()
        m = app.build_node_menu("a1")
        e = entries(m)
        check("node menu: Open, Rename, Set order, Move to, sep, Delete",
              [x[0] for x in e] == ["Open", "Rename\u2026", "Set order\u2026", "Move to", "-", "Delete\u2026"])
        check("normal node: all enabled", all(s == "normal" for l, s in e if l != "-"))
        ml = entries(m.nametowidget(m.entrycget(3, "menu")))
        check("Move to lists the category", [l for l, _ in ml] == ["Folder"])
        lm = entries(app.build_node_menu("L3"))
        d = dict(lm)
        check("locked node: Open ok, Rename/Set order/Move/Delete disabled",
              d["Open"] == "normal" and d["Rename\u2026"] == "disabled"
              and d["Set order\u2026"] == "disabled"
              and d["Move to"] == "disabled" and d["Delete\u2026"] == "disabled")
        check("stale node id gives an empty menu, no crash", entries(app.build_node_menu("zzz")) == [])

        stub_ask("Zed")
        m.invoke(1)
        check("menu Rename entry runs the rename", alpha["name"] == "Zed")
        m.nametowidget(m.entrycget(3, "menu")).invoke(0)
        check("menu Move-to entry moves the node", alpha in folder["child_nodes"])
        stub_yes(True)
        app.build_node_menu("b1").invoke(5)
        check("menu Delete entry deletes (after confirm)", find_node_by_id(tab["nodes"], "b1") is None)
        opened = []
        real_open = app.open_node
        app.open_node = lambda nid: opened.append(nid)
        app.build_node_menu("g1").invoke(0)
        app.open_node = real_open
        check("menu Open entry opens the node", opened == ["g1"])

        # bindings on real boxes
        tab, alpha, beta, gamma, folder, delta, chip = setup_nodes(app)
        app.refresh_workspace(); app.update()
        win, box = app._fileview_boxes["g1"]
        seq = app._context_seqs()[0]
        def all_widgets(w):
            yield w
            for c in w.winfo_children(): yield from all_widgets(c)
        check("right-click bound on the box and every child widget",
              all(bool(w.bind(seq)) for w in all_widgets(box)))
        captured = {}
        orig_popup = tk.Menu.tk_popup
        tk.Menu.tk_popup = lambda self_, x, y: captured.update(menu=self_)
        class Ev: x_root = 50; y_root = 60
        try:
            r = app._on_node_box_right_click(Ev, "g1")
        finally:
            tk.Menu.tk_popup = orig_popup
        check("handler pops the node menu and stops propagation", r == "break"
              and [x[0] for x in entries(captured["menu"])][0] == "Open")

        # ================= FILES: RENAME =================
        app2 = app
        t0 = app2.tabs[0]
        t0["title"] = "main"
        t0["nodes"] = [make_node("m", node_id="x1", blocks=[
            ("import_module", {"module": "helper"}),
            ("import_module", {"module": "main"}),          # self-import
        ])]
        t0["active_node_id"] = "x1"; app2.project_blocks = t0["nodes"][0]["blocks"]
        js_nodes = app2.build_initial_nodes_for_language("javascript")
        js_nodes[0]["blocks"] = [("import_module", {"module": "MAIN"}), ("import_module", {"module": "util"})]
        t1 = {"title": "helper", "language": "javascript", "nodes": js_nodes,
              "active_node_id": default_active_node_id(js_nodes), "filepath": None, "dirty": False}
        py_nodes = app2.build_initial_nodes_for_language("python")
        py_nodes[0]["blocks"] = [("import_module", {"module": "Helper"})]
        t2 = {"title": "util", "language": "python", "nodes": py_nodes,
              "active_node_id": default_active_node_id(py_nodes), "filepath": None, "dirty": False}
        app2.tabs[:] = [t0, t1, t2]
        app2.active_tab_index = 0
        app2.switch_to_files_view(); app2.files_view_code_mode = False
        app2.refresh_workspace(); app2.update()
        check("file wires resolved before rename", t1["file_references"] == [0, 2] or set(t1["file_references"]) == {0, 2})

        ok, msg, n = app2.rename_file(1, "Support")
        check("file rename succeeds", ok and t1["title"] == "Support")
        check("import in the active python tab rewritten", t0["nodes"][0]["blocks"][0][1]["module"] == "Support")
        check("case-insensitive import in another python tab rewritten",
              t2["nodes"][0]["blocks"][0][1]["module"] == "Support")
        check("count reports 2 rewrites", n == 2)
        check("the file's own imports are not rewritten (self-import untouched)",
              t0["nodes"][0]["blocks"][1][1]["module"] == "main")
        check("unrelated import untouched", js_nodes[0]["blocks"][1][1]["module"] == "util")
        check("changed tabs marked dirty", t0["dirty"] and t2["dirty"] and t1["dirty"])
        check("file wires survive the rename", 1 in t0["file_references"] and 1 in t2["file_references"])
        check("loaded pack restored after cross-language rewrite", app2.current_language == "python")

        ok, msg, n = app2.rename_file(0, "app")
        check("renaming the active file rewrites imports in the JS tab (other language)",
              js_nodes[0]["blocks"][0][1]["module"] == "app" and n == 1)
        ok, msg, n = app2.rename_file(2, "APP")
        check("duplicate title refused, case-insensitively", not ok and t2["title"] == "util")
        ok, msg, n = app2.rename_file(2, "  ")
        check("blank title refused", not ok)
        ok, msg, n = app2.rename_file(2, "util")
        check("same title is a no-op", ok and n == 0)
        ok, msg, n = app2.rename_file(9, "x")
        check("bad index is refused, no crash", not ok)
        stub_ask("Tools"); app2.rename_file_dialog(2)
        check("file rename dialog applies", t2["title"] == "Tools")
        stub_ask(None); app2.rename_file_dialog(2)
        check("cancelled file rename changes nothing", t2["title"] == "Tools")

        # file menu + bindings
        fm = app2.build_file_menu(1)
        check("file menu: Open, Rename, sep, Close file",
              [x[0] for x in entries(fm)] == ["Open", "Rename\u2026", "-", "Close file"])
        win, box = app2._filesview_boxes[1]
        check("right-click bound on every widget of a file box", all(bool(w.bind(seq)) for w in all_widgets(box)))
        opened = []
        real_of = app2.open_file_from_files_view
        app2.open_file_from_files_view = lambda i: opened.append(i)
        fm.invoke(0)
        app2.open_file_from_files_view = real_of
        check("file menu Open opens that file", opened == [1])

        # ================= FILES: CLOSE =================
        t2["dirty"] = True
        stub_yes(False)
        app2.build_file_menu(2).invoke(3)
        check("declining the unsaved-changes prompt keeps the file and the Files layer",
              len(app2.tabs) == 3 and app2.view_mode == "files")
        stub_yes(True)
        app2.build_file_menu(2).invoke(3); app2.update()
        check("closing a non-active file removes it", len(app2.tabs) == 2 and t2 not in app2.tabs)
        check("stays on the Files layer with one box per file",
              app2.view_mode == "files" and len(app2._filesview_boxes) == 2)
        app2.build_file_menu(0).invoke(3); app2.update()
        check("closing the ACTIVE file stays on the Files layer too",
              len(app2.tabs) == 1 and app2.view_mode == "files" and len(app2._filesview_boxes) == 1)
        stub_yes(True)
        app2.tabs[0]["dirty"] = False
        app2.close_file_from_files_view(0); app2.update()
        check("closing the last file leaves a fresh one (never zero tabs)",
              len(app2.tabs) == 1 and app2.view_mode == "files")
        app2.close_file_from_files_view(7)
        check("bad close index is a no-op", len(app2.tabs) == 1)
    finally:
        ui.simpledialog.askstring, ui.messagebox.askyesno, ui.messagebox.showwarning = real

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All box-menu tests passed.")

main()
