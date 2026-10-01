"""Node execution order: numbers drive generated-code order, entry point
is locked at 1, new nodes get the next number, changing to a taken
number swaps or unassigns (red), unassigned nodes still generate (last).
Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import (BlocklinerUI, make_node, sorted_function_nodes, normalize_orders,
                next_order, find_node_by_id)

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def assign(var, val):
    return ("assign_variable", {"variable": var, "value": val})

def names(tab):
    return [n["name"] for n in sorted_function_nodes(tab["nodes"])]

def code(app, tab):
    return app.generate_code_for_tab(tab, "python")

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()
    warned = []; asked = []
    real = (ui.simpledialog.askstring, ui.messagebox.askyesnocancel, ui.messagebox.showwarning)
    ui.messagebox.showwarning = lambda t, m, **k: warned.append(m)
    def stub_ask(v): ui.simpledialog.askstring = lambda *a, **k: v
    def stub_choice(v): ui.messagebox.askyesnocancel = lambda t, m, **k: (asked.append(m), v)[1]
    try:
        # ---- legacy nodes (no order key) keep tree order, then get numbered ----
        tab = app.tabs[0]
        a = make_node("A", node_id="a", blocks=[assign("a", "1")])
        b = make_node("B", node_id="b", blocks=[assign("b", "2")])
        c = make_node("C", node_id="c", blocks=[assign("c", "3")])
        folder = make_node("F", node_id="f", kind="category", child_nodes=[c])
        tab["nodes"] = [a, b, folder]; tab["active_node_id"] = "a"; tab["file_view_path"] = []
        app.project_blocks = a["blocks"]
        check("no order keys: generated in tree order (nested included)", names(tab) == ["A", "B", "C"])
        before = code(app, tab)
        check("normalize fills 1,2,3 in tree order", normalize_orders(tab["nodes"]) and [n["order"] for n in (a, b, c)] == [1, 2, 3])
        check("normalize is idempotent", normalize_orders(tab["nodes"]) is False)
        check("normalizing changes no generated code", code(app, tab) == before)
        check("categories get no order", "order" not in folder)
        check("next_order is max+1", next_order(tab["nodes"]) == 4)

        # ---- order drives codegen ----
        ok, msg, h = app.set_node_order(tab, c, 1, on_conflict="swap")
        check("swap 3<->1 succeeds", ok and h is a and c["order"] == 1 and a["order"] == 3)
        check("codegen follows the numbers", names(tab) == ["C", "B", "A"]
              and code(app, tab).index("c = 3") < code(app, tab).index("b = 2") < code(app, tab).index("a = 1"))

        # ---- conflict handling ----
        ok, msg, h = app.set_node_order(tab, b, 3)
        check("taken number without a choice: nothing changes, holder returned",
              (not ok) and h is a and b["order"] == 2 and a["order"] == 3)
        ok, msg, h = app.set_node_order(tab, b, 3, on_conflict="take")
        check("'take': node gets it, previous holder becomes unassigned",
              ok and b["order"] == 3 and a["order"] is None and "order" in a)
        check("unassigned node still generates, and last", names(tab) == ["C", "B", "A"] and "a = 1" in code(app, tab))
        # swap when self is unassigned -> other becomes unassigned
        ok, msg, h = app.set_node_order(tab, a, 1, on_conflict="swap")
        check("unassigned node swapping: holder becomes unassigned, node gets number",
              ok and a["order"] == 1 and c["order"] is None)
        ok, _, _ = app.set_node_order(tab, c, 2)
        check("giving an unassigned node a free number works", ok and c["order"] == 2)

        # ---- validation ----
        for bad in (0, -3, "2", 2.5, True):
            ok, msg, h = app.set_node_order(tab, b, bad)
            check(f"invalid value {bad!r} refused", (not ok) and h is None)
        ok, msg, h = app.set_node_order(tab, b, b["order"])
        check("same number is a harmless no-op", ok and h is None)
        ok, _, _ = app.set_node_order(tab, folder, 5)
        check("category refuses an order", not ok)

        # ---- entry point: locked, 1, untouchable ----
        for lang in ("cpp", "csharp"):
            nodes = app.build_initial_nodes_for_language(lang)
            entry = [n for n in ui.function_nodes_in_tree_order(nodes)][0]
            check(f"{lang}: entry point is locked with order 1", entry["locked"] and entry["order"] == 1)
        entry = app.build_initial_nodes_for_language("cpp")[0]
        tab["nodes"].insert(0, entry)
        n1 = make_node("N1", node_id="n1", order=next_order(tab["nodes"]))
        tab["nodes"].append(n1)
        check("new node gets the next number", n1["order"] == 4)
        ok, msg, h = app.set_node_order(tab, entry, 9)
        check("locked entry can't be renumbered", not ok and entry["order"] == 1)
        ok, msg, h = app.set_node_order(tab, b, 1, on_conflict="take")
        check("can't take the locked entry's 1", not ok and "locked" in msg and entry["order"] == 1)

        # ---- create_node assigns the next number ----
        tab["file_view_path"] = []
        stub_ask("Fresh")
        app.view_mode = "file"
        before_max = next_order(tab["nodes"])
        app.create_node()
        fresh = [n for n in ui.function_nodes_in_tree_order(tab["nodes"]) if n["name"] == "Fresh"][0]
        check("create_node numbers the new node max+1", fresh["order"] == before_max)

        # ---- UI: badge, red outline, dialog ----
        tab["file_view_path"] = []
        app.view_mode = "file"; app.refresh_workspace(); app.update()
        def badge_text(nid):
            box = app._fileview_boxes[nid][1]
            found = []
            def walk(w):
                for ch in w.winfo_children():
                    if isinstance(ch, tk.Label) and ch.cget("text").startswith("#"): found.append(ch.cget("text"))
                    walk(ch)
            walk(box); return found
        check("badge shows the number", badge_text("n1") == ["#4"])
        check("entry badge shows #1", badge_text(entry["id"]) == ["#1"])
        b["order"] = None; app.refresh_workspace(); app.update()
        check("unassigned shows #?", badge_text("b") == ["#?"])
        check("unassigned box is outlined red",
              str(app._fileview_boxes["b"][1].cget("highlightbackground")).lower() == "#ff3b3b")
        check("assigned box keeps the normal outline",
              str(app._fileview_boxes["n1"][1].cget("highlightbackground")) == ui.DARK_BORDER)

        stub_ask("7"); app.set_node_order_dialog("b"); app.update()
        check("dialog assigns a free number", b["order"] == 7)
        stub_ask("abc"); warned.clear(); app.set_node_order_dialog("b")
        check("non-number warns, changes nothing", len(warned) == 1 and b["order"] == 7)
        stub_ask(""); warned.clear(); app.set_node_order_dialog("b")
        check("blank is refused (a number is required)", len(warned) == 1 and b["order"] == 7)
        stub_ask(None); app.set_node_order_dialog("b")
        check("cancel changes nothing", b["order"] == 7)
        stub_ask(str(n1["order"])); stub_choice(True); asked.clear()
        app.set_node_order_dialog("b")
        check("collision prompt -> Yes swaps", len(asked) == 1 and b["order"] == 4 and n1["order"] == 7)
        stub_ask("7"); stub_choice(False)
        app.set_node_order_dialog("b")
        check("collision prompt -> No takes it, other goes unassigned", b["order"] == 7 and n1["order"] is None)
        held = c["order"]
        stub_ask(str(held)); stub_choice(None)
        app.set_node_order_dialog("b")
        check("collision prompt -> Cancel changes nothing",
              b["order"] == 7 and c["order"] == held and n1["order"] is None)
        warned.clear(); stub_ask("1"); app.set_node_order_dialog("b")
        check("number held by locked node warns", len(warned) == 1 and b["order"] == 7)

        # ---- menu ----
        m = app.build_node_menu("b")
        labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) != "separator"]
        check("node menu has 'Set order…'", "Set order\u2026" in labels)
        m2 = app.build_node_menu(entry["id"])
        idx = [i for i in range(m2.index("end") + 1) if m2.type(i) != "separator" and m2.entrycget(i, "label").startswith("Set order")][0]
        check("Set order… disabled on the locked entry", str(m2.entrycget(idx, "state")) == "disabled")
        cm = app.build_node_menu("f")
        clabels = [cm.entrycget(i, "label") for i in range(cm.index("end") + 1) if cm.type(i) != "separator"]
        check("category menu has no order entry", not any(l.startswith("Set order") for l in clabels))
    finally:
        ui.simpledialog.askstring, ui.messagebox.askyesnocancel, ui.messagebox.showwarning = real

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All node-order tests passed.")

main()
