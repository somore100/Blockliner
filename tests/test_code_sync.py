"""Code panel -> blocks sync: modes (line / char / manual), the amber decision
banner (Replace all / Keep blocks / See all), the one-time warning, hidden
markers, new/missing nodes. Run under Xvfb."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import code_sync as C
import portable as P
import ui_codesync
from ui import BlocklinerUI
from ui_common import DEFAULT_SETTINGS
from nodes_model import make_node, function_nodes_in_tree_order

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def pure():
    check("defaults", DEFAULT_SETTINGS["code_sync_mode"] == "line" and DEFAULT_SETTINGS["code_sync_confirm"] is True and DEFAULT_SETTINGS["code_edit_warned"] is False)
    check("mode normalize", [C.normalize_sync_mode(x) for x in ("line", "char", "manual", "zz", None)] == ["line", "char", "manual", "line", "line"])
    check("same_code ignores blank lines + trailing spaces", C.same_code("a\n\nb  \n", "a\nb"))
    check("same_code sees real changes", not C.same_code("a\nb", "a\nc") and not C.same_code("a", "a\n  a"))
    old, new = ["a", "b", "c"], ["a", "B", "c", "d"]
    ops = C.diff_blocks(old, new)
    check("diff tags", [o[0] for o in ops] == ["equal", "replace", "equal", "insert"])
    o_blocks, n_blocks = ["A", "B", "C"], ["A", "b2", "C", "D"]
    check("merge: code wins", C.merge_blocks(o_blocks, n_blocks, ops) == ["A", "b2", "C", "D"])
    check("merge: keep replace, insert still applied", C.merge_blocks(o_blocks, n_blocks, ops, {1}) == ["A", "B", "C", "D"])
    dops = C.diff_blocks(["a", "b"], ["a"])
    check("merge: delete applied / kept", C.merge_blocks(["A", "B"], ["A"], dops) == ["A"] and C.merge_blocks(["A", "B"], ["A"], dops, {1}) == ["A", "B"])
    check("line_of_block counts multi-line blocks", C.line_of_block(["x\ny\nz", "q"], 1) == 4 and C.line_of_block(["x"], 0) == 1)
    m = C.describe_change("main", "replace", 3, ["print(a)"], ["print(b)"])
    check("message names node, line, old, new", "main" in m and "line 3" in m and "print(a)" in m and "print(b)" in m and "replaced" in m)
    check("delete message", "removed" in C.describe_change("main", "delete", 2, ["x = 1"], []))
    check("long text is shortened", len(C.describe_change("n", "delete", 1, ["z" * 500], [])) < 200)

def main():
    pure()
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    warns, infos = [], []
    ui_codesync.messagebox.showwarning = lambda *a, **k: warns.append(a)
    ui_codesync.messagebox.showinfo = lambda *a, **k: infos.append(a)
    app.maybe_notify = lambda t, m: infos.append((t, m))
    app.save_app_settings = lambda: None
    t = app.code_text

    def setup(code="print(1)\nx = 2\nif x:\n    print(x)\nname = 'bob'\n"):
        app.settings.update(code_edit_warned=True, code_sync_mode="manual", code_sync_confirm=True, safe_mode=True, show_markers=True, save_format="sidecar")
        tab = app.tabs[app.active_tab_index]
        fn = function_nodes_in_tree_order(tab["nodes"])
        fn[0]["blocks"] = app.import_code_to_blocks(code)[0]
        tab["nodes"] = [fn[0]]
        tab["active_node_id"] = fn[0]["id"]; app.project_blocks = fn[0]["blocks"]
        app.hide_sync_banner(); app.update_generated_code(); app.update()
        return tab, fn[0]
    def text(): return t.get("1.0", "end-1c")
    def line_of(s): return next(i + 1 for i, l in enumerate(text().split("\n")) if s in l)
    def replace_line(s, new):
        ln = line_of(s); t.delete(f"{ln}.0", f"{ln}.end"); t.insert(f"{ln}.0", new)
    def blocks_code(node): return app._code_for_blocks("python", node["blocks"])
    def click(label):
        for w in app.sync_banner.winfo_children():
            for b in w.winfo_children() if w.winfo_class() == "Frame" else [w]:
                if b.winfo_class() == "Button" and b.cget("text").startswith(label):
                    b.invoke(); app.update(); return True
        return False
    def wait(n=8):
        for _ in range(n): app.update(); time.sleep(0.05)

    # --- manual mode basics
    tab, node = setup()
    plan = app.compute_sync_plan()
    check("unedited panel: nothing to sync (round trip is stable)", plan["status"] == "ok" and not plan["nodes"] and not plan["adds"] and not plan["hunks"])
    app.sync_code_now()
    check("unedited + manual button: says already in sync", any("In sync" in str(i) for i in infos) and app.sync_banner is None)
    replace_line("x = 2", "x = 99")
    wait()
    check("manual mode: typing does not sync by itself", "x = 2" in blocks_code(node) and app.sync_banner is None)
    app.sync_code_now()
    check("manual button: amber banner appears (blocks not touched yet)", app.sync_banner is not None and "x = 2" in blocks_code(node))
    labels = " ".join(w.cget("text") for w in app.sync_banner.winfo_children() if w.winfo_class() == "Label")
    check("banner says node, line, old and new", "main" in labels and "line 2" in labels and "x = 2" in labels and "x = 99" in labels and "Continue?" in labels)
    check("banner has a different background", app.sync_banner.cget("bg") == ui_codesync.SYNC_BANNER_BG)
    check("Replace all is blue", any(b.cget("bg") == ui_codesync.SYNC_BLUE and b.cget("text") == "Replace all" for w in app.sync_banner.winfo_children() for b in w.winfo_children() if b.winfo_class() == "Button"))
    t.mark_set("insert", "3.2")
    check("click Replace all", click("Replace all"))
    check("Replace all: blocks now hold the typed code", "x = 99" in blocks_code(node) and "x = 2" not in blocks_code(node))
    check("Replace all: banner gone, panel regenerated from blocks", app.sync_banner is None and "x = 99" in text() and P.NODE_MARKER_RE.search(text()))
    check("Replace all: active node pointer updated", app.project_blocks is node["blocks"] and tab["dirty"])
    check("Replace all: caret kept", str(t.index("insert")).startswith("3."))

    # --- keep blocks
    tab, node = setup()
    replace_line("x = 2", "x = 99"); app.sync_code_now()
    check("click Keep blocks", click("Keep blocks"))
    check("Keep blocks: typed code discarded, blocks untouched", "x = 2" in blocks_code(node) and "x = 99" not in text() and app.sync_banner is None)

    # --- see all
    tab, node = setup()
    replace_line("x = 2", "x = 99"); replace_line("name = 'bob'", "name = 'amy'"); app.sync_code_now()
    labels = " ".join(w.cget("text") for w in app.sync_banner.winfo_children() if w.winfo_class() == "Label")
    check("two changes: banner counts them", "2 changes" in labels)
    click("See all")
    dlg = app._sync_review_dialog
    check("review dialog has one checkbox per change, all ticked", len(dlg.review_vars) == 2 and all(v.get() for _h, v in dlg.review_vars))
    dlg.review_vars[0][1].set(False)   # keep the blocks for the first change
    dlg.apply_selected(); app.update()
    bc = blocks_code(node)
    check("review: unticked change keeps its block, ticked one is replaced", "x = 2" in bc and "name = 'amy'" in bc and "name = 'bob'" not in bc)

    # --- a pending banner dies when blocks rewrite the panel
    tab, node = setup(); replace_line("x = 2", "x = 99"); app.sync_code_now()
    check("banner is up", app.sync_banner is not None)
    app.update_generated_code()
    check("panel regenerated from blocks: stale banner is removed", app.sync_banner is None and app._sync_pending is None)

    # --- inserts need no decision
    tab, node = setup()
    ln = line_of("x = 2"); t.insert(f"{ln}.end", "\ny = 7")
    app.sync_code_now()
    check("added line: applied without a banner", app.sync_banner is None and "y = 7" in blocks_code(node) and "x = 2" in blocks_code(node))

    # --- confirm off
    tab, node = setup(); app.settings["code_sync_confirm"] = False
    replace_line("x = 2", "x = 5"); app.sync_code_now()
    check("confirm off: replaced right away", app.sync_banner is None and "x = 5" in blocks_code(node))

    # --- line mode
    tab, node = setup(); app.settings["code_sync_mode"] = "line"
    ln = line_of("x = 2"); t.mark_set("insert", f"{ln}.0"); replace_line("x = 2", "x = 11"); wait()
    check("line mode: still on the edited line -> no sync", app.sync_banner is None and "x = 2" in blocks_code(node))
    t.focus_force(); app.update(); t.mark_set("insert", "2.0"); t.event_generate("<KeyRelease>"); wait()
    check("line mode: leaving the line syncs (banner for a replace)", app.sync_banner is not None)
    click("Replace all")
    check("line mode: result applied", "x = 11" in blocks_code(node))
    tab, node = setup(); app.settings["code_sync_mode"] = "line"; app.settings["code_sync_confirm"] = False
    ln = line_of("name ="); t.mark_set("insert", f"{ln}.end"); t.insert(f"{ln}.end", "\nz = 3"); wait()
    check("line mode: Enter (caret moves to a new line) syncs the line just finished", "z = 3" in blocks_code(node))

    # --- char mode
    tab, node = setup(); app.settings["code_sync_mode"] = "char"; app.settings["code_sync_confirm"] = False
    ln = line_of("x = 2"); t.mark_set("insert", f"{ln}.0"); replace_line("x = 2", "x = 21"); wait(10)
    check("char mode: syncs without leaving the line", "x = 21" in blocks_code(node))
    tab, node = setup(); app.settings["code_sync_mode"] = "char"; app.settings["code_sync_confirm"] = False
    runs = []; real = app.run_code_sync
    app.run_code_sync = lambda manual=False: (runs.append(1), real(manual))[1]
    ln = line_of("x = 2"); t.mark_set("insert", f"{ln}.0")
    for ch in "x = 3":
        t.insert(f"{ln}.end", " ")
    wait(10)
    check("char mode: five quick edits run ONE sync (debounced)", len(runs) == 1)
    del app.run_code_sync

    # --- one-time warning
    tab, node = setup(); app.settings["code_edit_warned"] = False; warns.clear()
    t.insert("end", "# a\n"); t.insert("end", "# b\n")
    check("first edit shows the warning exactly once", len(warns) == 1 and "mistakes" in str(warns[0]) and app.settings["code_edit_warned"] is True)
    app.settings["code_edit_warned"] = False; warns.clear()
    app.update_generated_code()
    check("regeneration by Blockliner does not warn", not warns)
    ln = line_of("start"); t.insert(f"{ln}.5", "zz")
    check("refused (safe mode) edit does not warn", not warns)

    # --- hidden markers
    tab, node = setup(); app.settings["show_markers"] = False; app.update_generated_code(); infos.clear()
    t.insert("1.0", "q = 1\n")
    try:
        app.sync_code_now(); raised = False
    except Exception as exc:  # noqa
        raised = True
    check("markers hidden: sync does not raise", not raised)
    check("markers hidden: manual sync explains, changes nothing", any("Show markers" in str(i) for i in infos) and "q = 1" not in blocks_code(node))
    app.settings["show_markers"] = True; app.update_generated_code()

    # --- new node / missing node (safe mode off)
    tab, node = setup(); app.settings["safe_mode"] = False; app.settings["code_sync_confirm"] = False
    t.insert("end", "# $$$blockliner:node:fresh$$$ start\nw = 1\n# $$$blockliner:node:fresh$$$ end\n")
    app.sync_code_now()
    names = [n["id"] for n in function_nodes_in_tree_order(tab["nodes"])]
    fresh = next((n for n in function_nodes_in_tree_order(tab["nodes"]) if n["id"] == "fresh"), None)
    check("unknown marker id becomes a new node with its code", fresh is not None and "w = 1" in blocks_code(fresh) and node["id"] in names)
    t.delete("1.0", "end"); t.insert("1.0", "# $$$blockliner:node:fresh$$$ start\nw = 1\n# $$$blockliner:node:fresh$$$ end\n")
    app.sync_code_now()
    check("node whose markers vanished is kept, never deleted", node["id"] in [n["id"] for n in function_nodes_in_tree_order(tab["nodes"])])

    # --- re-entrancy
    tab, node = setup(); app.settings["code_sync_confirm"] = False
    replace_line("x = 2", "x = 8")
    applied = []; real_apply = app.apply_sync_plan
    def nested(plan, keep=frozenset()):
        applied.append(1)
        if len(applied) == 1:
            app.run_code_sync()          # a second sync fired while the first is running
        return real_apply(plan, keep)
    app.apply_sync_plan = nested
    app.sync_code_now()
    del app.apply_sync_plan
    check("a sync started during a sync is ignored", len(applied) == 1 and "x = 8" in blocks_code(node))

    # --- stale plan
    tab, node = setup(); app.settings["code_sync_confirm"] = True
    replace_line("x = 2", "x = 77"); app.sync_code_now(); plan = app._sync_pending
    app.hide_sync_banner(); app.tabs.append({"title": "other", "language": "python", "nodes": [make_node("main", node_id="main", blocks=[])], "active_node_id": "main", "filepath": None, "dirty": False})
    app.switch_to_tab(len(app.tabs) - 1)
    app.apply_sync_plan(plan)
    check("plan for another tab is ignored", "x = 2" in app._code_for_blocks("python", node["blocks"]))
    app.switch_to_tab(0)

    # --- toolbar
    def walk(w):
        yield w
        for c in w.winfo_children(): yield from walk(c)
    texts = {w.cget("text") for w in walk(app) if w.winfo_class() in ("Button", "TButton") and "text" in w.keys()}
    check("Sync button exists in the code panel", any("Sync code" in x for x in texts))
    check("old 'Code -> Blocks' toolbar button is gone", not any(x.endswith("Code \u2192 Blocks") for x in texts))
    menu_labels = [m.entrycget(i, "label") for m in app.topbar_menus.values() for i in range(m.index("end") + 1) if m.type(i) == "command"]
    check("Open Code File is in the File menu", any("Open Code File" in x for x in menu_labels))

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
