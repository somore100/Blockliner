"""Open several selected nodes together in one Blocks view (multi_open.py +
ui_multiopen.py). Pure logic first, then the real window headless (Xvfb)."""
import os, sys, json, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import multi_open as mo
import project_file
from nodes_model import make_node, find_node_by_id
from ui import BlocklinerUI
from ui_multiopen import NodeMarkerRow
from ui_widgets import BlockWidget

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def P(text): return ("print_output", {"value": repr(text)})
def vals(blocks): return [b[1]["value"].strip("'") for b in blocks if not mo.is_marker(b)]
def labels(menu): return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
def texts(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, (tk.Label, tk.Button)): out.append(ch.cget("text"))
        out += texts(ch)
    return out

def pure():
    a = make_node("a", node_id="a1", blocks=[P("A1"), P("A2")])
    b = make_node("b", node_id="b1", blocks=[P("B1")])
    c = make_node("c", node_id="c1", blocks=[])
    comb = mo.build([a, b, c])
    check("build: one marker per node, in order", [mo.marker_node_id(e) for e in comb if mo.is_marker(e)] == ["a1", "b1", "c1"])
    check("build: blocks sit under their marker", [("M" if mo.is_marker(e) else e[1]["value"]) for e in comb] ==
          ["M", "'A1'", "'A2'", "M", "'B1'", "M"])
    parts = mo.split(comb, ["a1", "b1", "c1"])
    check("split round-trips", vals(parts["a1"]) == ["A1", "A2"] and vals(parts["b1"]) == ["B1"] and parts["c1"] == [])
    check("split never leaks a marker", not any(mo.is_marker(e) for p in parts.values() for e in p))
    lead = [P("L")] + comb
    check("blocks above the first marker go to the first node", vals(mo.split(lead, ["a1", "b1", "c1"])["a1"]) == ["L", "A1", "A2"])
    nomark = [e for e in comb if not (mo.is_marker(e) and mo.marker_node_id(e) == "b1")]
    check("a vanished marker folds its blocks into the node above (nothing lost)",
          vals(mo.split(nomark, ["a1", "b1", "c1"])["a1"]) == ["A1", "A2", "B1"])
    check("unknown marker id is ignored", vals(mo.split([mo.make_marker("zz"), P("X")], ["a1"])["a1"]) == ["X"])
    check("real_count skips markers", mo.real_count(comb) == 3)
    x = make_node("x", node_id="x", blocks=[]); y = make_node("y", node_id="y", blocks=[]); z = make_node("z", node_id="z", blocks=[])
    x["order"], y["order"], z["order"] = 3, None, 1
    check("order_nodes: run order, unassigned last", [n["id"] for n in mo.order_nodes([x, y, z])] == ["z", "x", "y"])
    y["ignored"] = True
    check("order_nodes keeps ignored nodes", len(mo.order_nodes([x, y, z])) == 3)

def main():
    pure()
    import ui_tabs
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.settings["confirm_delete"] = False
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]

    def fresh():
        a = make_node("alpha", node_id="a1", blocks=[P("A1"), P("A2")]); a["order"] = 1
        b = make_node("beta", node_id="b1", blocks=[P("B1"), P("B2")]); b["order"] = 3
        c = make_node("gamma", node_id="c1", blocks=[P("C1")]); c["order"] = 2
        cat = make_node("cat", node_id="k1", kind="category", child_nodes=[])
        tab["nodes"] = [a, b, c, cat]; tab["active_node_id"] = "a1"; tab["file_view_path"] = []
        for i, n in enumerate(tab["nodes"]): n["canvas_x"], n["canvas_y"] = 20 + 260 * (i % 3), 20 + 200 * (i // 3)
        app.selected_nodes().clear()
        app.project_blocks = a["blocks"]; app._multi = None
        app.switch_to_file_view(); app.update(); app.update()
        return a, b, c

    a, b, c = fresh()
    gen = lambda: app.generate_code_for_tab(tab, "python")

    # ---- nothing selected / one selected: no "open together"
    check("no selection: no open-together entry", not any("together" in l for l in labels(app.build_node_menu("a1"))))
    app.toggle_node_selected("a1")
    check("one selected: still no open-together entry", not any("together" in l for l in labels(app.build_node_menu("a1"))))
    app.open_selected_nodes(); app.update()
    check("one selected: plain open of that node", app.view_mode == "node" and app.project_blocks is a["blocks"] and app.multi_state() is None)
    a, b, c = fresh()

    # ---- select + offered everywhere
    app.toggle_node_selected("a1"); app.toggle_node_selected("c1"); app.toggle_node_selected("k1"); app.toggle_node_selected("b1")
    app.update()
    check("a category in the selection does not count", len(app.selected_function_nodes()) == 3)
    check("right-click menu offers the combined open", "Open 3 selected together" in labels(app.build_node_menu("a1")))
    nav = " ".join(texts(app.node_nav_frame))
    check("nav bar shows an Open-together button", "Open 3 selected together" in nav)
    app.toggle_node_selected("k1")
    app.clear_node_selection(); app.update()
    check("button disappears when the selection is cleared", "together" not in " ".join(texts(app.node_nav_frame)))
    for i in ("a1", "c1", "b1"): app.toggle_node_selected(i)

    # ---- open together
    app.open_selected_nodes(); app.update(); app.update()
    check("Blocks layer shows the combined list", app.view_mode == "node" and app.multi_active())
    check("run order: alpha(1), gamma(2), beta(3)", [n["id"] for n in app.multi_nodes()] == ["a1", "c1", "b1"])
    check("combined list = markers + blocks", mo.real_count(app.project_blocks) == 5 and len(app.project_blocks) == 8)
    rows = [w for w in app.workspace_frame.winfo_children() if isinstance(w, NodeMarkerRow)]
    bws = [w for w in app.workspace_frame.winfo_children() if isinstance(w, BlockWidget)]
    check("one separator row per node, one widget per block", len(rows) == 3 and len(bws) == 5)
    check("separator names the node and its run order", any("alpha" in t and "▶1" in t for t in texts(rows[0])))
    check("selection cleared after opening", app.selected_nodes() == set())
    crumb = " ".join(texts(app.node_nav_frame))
    check("nav says it is editing 3 nodes together", "3 nodes together" in crumb)
    nums = [t for w in bws for t in texts(w.winfo_children()[0]) if t.isdigit()]
    check("block numbers run 1..5 (separators are not counted)", nums == ["1", "2", "3", "4", "5"])
    check("block count counts blocks, not separators", app.block_count_label.cget("text").startswith("5 block"))
    check("separators never reach a node", not any(mo.is_marker(e) for n in (a, b, c) for e in n["blocks"]))
    check("generated code is in run order and complete", [s for s in ("A1", "A2", "C1", "B1", "B2") if s in gen()] == ["A1", "A2", "C1", "B1", "B2"]
          and gen().index("C1") < gen().index("B1"))

    # ---- ordinary edits land in the right node
    app.project_blocks.append(P("NEW")); app.mark_active_tab_dirty(); app.refresh_workspace(); app.update()
    check("appended block goes to the LAST node", vals(b["blocks"]) == ["B1", "B2", "NEW"] and vals(a["blocks"]) == ["A1", "A2"])
    i_c1 = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'C1'")
    app.project_blocks[i_c1] = ("print_output", {"value": "'C1x'"})       # edit replaces the tuple
    app.refresh_workspace(); app.update()
    check("editing the FIRST block of a node keeps it in that node", vals(c["blocks"]) == ["C1x"] and vals(a["blocks"]) == ["A1", "A2"])
    i_b1 = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'B1'")
    app.project_blocks[i_b1][1]["value"] = "'B1y'"                         # in-place param edit
    app.refresh_workspace()
    check("in-place param edit propagates", vals(b["blocks"])[0] == "B1y")

    # moving across a separator moves the block to the neighbouring node
    i_b1 = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'B1y'")
    app.move_block_up(i_b1); app.update()
    check("Up on a node's first block moves it to the end of the node above", vals(c["blocks"]) == ["C1x", "B1y"] and vals(b["blocks"]) == ["B2", "NEW"])
    i_b1 = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'B1y'")
    app.move_block_down(i_b1); app.update()
    check("Down brings it back", vals(c["blocks"]) == ["C1x"] and vals(b["blocks"]) == ["B1y", "B2", "NEW"])
    i = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'A1'")
    app.move_block_up(i); app.update()
    check("Up on the very first block is a no-op", vals(a["blocks"]) == ["A1", "A2"])
    i = next(i for i, e in enumerate(app.project_blocks) if not mo.is_marker(e) and e[1]["value"] == "'A2'")
    app.delete_block(i); app.update()
    check("delete removes from the right node", vals(a["blocks"]) == ["A1"] and vals(c["blocks"]) == ["C1x"])
    # drag-reorder across a node boundary
    i_last_b = len(app.project_blocks) - 1
    app.move_block_to(i_last_b, 0); app.update()
    check("drag to the very top lands in the first node", vals(a["blocks"])[0] == "NEW" and "NEW" not in vals(b["blocks"]))
    total = sorted(vals(a["blocks"]) + vals(b["blocks"]) + vals(c["blocks"]))
    check("nothing lost or duplicated by all that", total == sorted(["NEW", "A1", "C1x", "B1y", "B2"]))

    # ---- drop target knows the separators
    rows = [w for w in app.workspace_frame.winfo_children() if isinstance(w, NodeMarkerRow)]
    r = rows[1]
    idx, _y = app.drop_target(r.winfo_rooty() + 1)
    check("dropping on a separator's top half = just above it (end of the previous node)", idx == r.index)
    first_after = [w for w in app.workspace_frame.winfo_children() if isinstance(w, BlockWidget) and w.index == r.index + 1][0]
    idx, _y = app.drop_target(first_after.winfo_rooty() + 1)
    check("dropping on the node's first block = before it, inside that node", idx == first_after.index)

    # ---- flush is not only a refresh thing
    app.project_blocks.append(P("LATE"))
    app.sync_active_tab_state()
    check("sync_active_tab_state hands each node its own part (never the whole list)",
          vals(b["blocks"])[-1] == "LATE" and not any(mo.is_marker(e) for n in (a, b, c) for e in n["blocks"]) and len(a["blocks"]) < 4)
    data = json.loads(project_file.dumps_workspace([{"title": "t", "language": "python", "nodes": tab["nodes"], "active_node_id": "a1"}], 0))
    check("saved project has no separators", "__node__" not in json.dumps(data))
    check("the active node's list is not clobbered by the combined list", a["blocks"] is not app.project_blocks)

    # ---- code-panel / Nodes-layer replacement while combined
    new_b = [P("R1"), P("R2")]
    app._replace_node_blocks(tab, b, new_b)
    app.update()
    check("replacing one node's blocks re-reads the combined view", vals(app.project_blocks)[-2:] == ["R1", "R2"] and app.multi_active())
    app.refresh_workspace()
    check("...and survives the next refresh", vals(b["blocks"]) == ["R1", "R2"])
    # a separator deleted by accident: blocks fold into the node above, none lost
    j = next(i for i, e in enumerate(app.project_blocks) if mo.is_marker(e) and mo.marker_node_id(e) == "b1")
    before = sorted(vals(a["blocks"]) + vals(b["blocks"]) + vals(c["blocks"]))
    app.project_blocks.pop(j); app.refresh_workspace(); app.update()
    after = sorted(vals(a["blocks"]) + vals(b["blocks"]) + vals(c["blocks"]))
    check("losing a separator loses no block", before == after)
    check("the separator is put back", sum(1 for e in app.project_blocks if mo.is_marker(e)) == 3)

    # ---- clear
    ui_tabs.messagebox.askyesno = lambda *a, **k: True
    app.clear_all(); app.update()
    check("Clear empties every open node but keeps the combined view", all(n["blocks"] == [] for n in (a, b, c)) and app.multi_active()
          and sum(1 for e in app.project_blocks if mo.is_marker(e)) == 3)

    # ---- leaving
    a, b, c = fresh()
    for i in ("a1", "b1"): app.toggle_node_selected(i)
    app.open_selected_nodes(); app.update()
    app.project_blocks.append(P("ZED")); app.refresh_workspace()
    app.switch_to_file_view(); app.update()
    check("Nodes layer: combined state gone, active node's own list back", app.multi_state() is None and app.project_blocks is a["blocks"])
    check("edits survived leaving", vals(b["blocks"])[-1] == "ZED" and not any(mo.is_marker(e) for n in (a, b) for e in n["blocks"]))
    app.toggle_node_selected("a1"); app.toggle_node_selected("b1")
    app.open_selected_nodes(); app.update()
    app.open_node("b1"); app.update()
    check("opening one node afterwards is a plain single open", app.multi_state() is None and app.project_blocks is b["blocks"]
          and not any(isinstance(w, NodeMarkerRow) for w in app.workspace_frame.winfo_children()))
    check("single view crumb has no 'together'", "together" not in " ".join(texts(app.node_nav_frame)))
    # tab switch while combined
    app.toggle_node_selected("a1"); app.toggle_node_selected("b1")
    app.switch_to_file_view(); app.update()
    app.toggle_node_selected("a1"); app.toggle_node_selected("b1")
    app.open_selected_nodes(); app.update()
    app.project_blocks.append(P("TABX"))
    app.new_tab(); app.update()
    check("switching tab flushes and drops the combined view", app.multi_state() is None and vals(b["blocks"])[-1] == "TABX"
          and app.project_blocks is not b["blocks"])
    app.switch_to_tab(0); app.update()
    check("coming back shows a normal single node", app.multi_state() is None and not any(isinstance(w, NodeMarkerRow) for w in app.workspace_frame.winfo_children()))
    # wholesale replace
    app.switch_to_file_view(); app.toggle_node_selected("a1"); app.toggle_node_selected("b1")
    app.open_selected_nodes(); app.update()
    keep = vals(b["blocks"])
    app.set_project_blocks([P("ONLY")]); app.update()
    check("a wholesale replace leaves the combined view and touches only the active node",
          app.multi_state() is None and vals(a["blocks"]) == ["ONLY"] and vals(b["blocks"]) == keep)

    # ---- ignored nodes can be opened on purpose; deselect via sidebar not needed
    a, b, c = fresh()
    b["ignored"] = True
    for i in ("a1", "b1"): app.toggle_node_selected(i)
    app.open_selected_nodes(); app.update()
    check("an ignored node can be opened together with others", [n["id"] for n in app.multi_nodes()] == ["a1", "b1"])
    check("...and its separator says so", any("ignored" in t for r in app.workspace_frame.winfo_children() if isinstance(r, NodeMarkerRow) for t in texts(r)))
    check("...but it is still left out of generated code", "B1" not in gen())

    app.destroy()
    print("\nFAILURES:", FAILURES if FAILURES else "none")
    sys.exit(1 if FAILURES else 0)

main()
