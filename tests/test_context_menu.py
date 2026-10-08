"""Workspace right-click menu: per-layer top entry, Panels submenu,
cursor placement of new nodes/categories/files, bindings."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import BlocklinerUI, get_block_attr

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def labels(menu):
    out = []
    for i in range(menu.index("end") + 1 if menu.index("end") is not None else 0):
        t = menu.type(i)
        out.append("-" if t == "separator" else menu.entrycget(i, "label"))
    return out

def idx(menu, label):
    for i in range(menu.index("end") + 1):
        if menu.type(i) != "separator" and menu.entrycget(i, "label") == label:
            return i
    raise KeyError(label)

def sub(menu, label):
    return menu.nametowidget(menu.entrycget(idx(menu, label), "menu"))

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()
    pm = app.panels
    tab = app.tabs[0]

    # ---------- bindings ----------
    check("right-click bound on workspace canvas", bool(app.workspace_canvas.bind("<Button-3>")))
    check("right-click bound on block-editor frame", bool(app.workspace_frame.bind("<Button-3>")))

    # ---------- Blocks layer ----------
    check("starts at Blocks layer", app.view_mode == "node")
    m = app.build_workspace_menu((10, 20))
    L = labels(m)
    check("Blocks layer: 'Add block' is the top entry", L[0].endswith("Add block"))
    check("Blocks layer: separator then Panels", L[1] == "-" and L[2].endswith("Panels"))
    check("no node/category/file entries at Blocks layer",
          not any(("node" in x.lower() or "categ" in x.lower() or "file" in x.lower()) for x in L))
    add = sub(m, L[0])
    cats = [c for c in app.get_ordered_categories() if app.blocks_by_category.get(c)]
    check("categories mirror the palette's order", labels(add) == cats and len(cats) >= 2)
    total = 0
    ok_names = True
    for c in cats:
        names = labels(sub(add, c))
        expect = [get_block_attr(b, "display_name", "Unknown") for b in app.blocks_by_category[c]]
        ok_names &= (names == expect); total += len(names)
    check("every category lists exactly its blocks", ok_names)
    check("menu offers all palette blocks", total == sum(len(v) for v in app.blocks_by_category.values()))

    calls = []
    orig_edit = app.edit_block_params
    app.edit_block_params = lambda mod, params, add_mode=True, **k: calls.append((mod, add_mode))
    first_cat = cats[0]
    cm = sub(add, first_cat)
    cm.invoke(0)
    check("picking a block opens the add dialog for THAT block",
          len(calls) == 1 and calls[0][0] is app.blocks_by_category[first_cat][0] and calls[0][1] is True)
    app.edit_block_params = orig_edit

    saved = app.blocks_by_category
    app.blocks_by_category = {}
    m2 = app.build_workspace_menu((0, 0))
    check("no blocks for the language -> 'Add block' disabled",
          m2.entrycget(0, "state") == "disabled")
    app.blocks_by_category = saved

    # ---------- Panels submenu at Blocks layer ----------
    pmenu = sub(m, L[2])
    check("Panels lists palette + code at Blocks layer",
          labels(pmenu) == ["Block Palette", "Generated Code"])
    check("checkbuttons reflect visibility (both on)",
          m._vars[0].get() is True and m._vars[1].get() is True)
    pmenu.invoke(idx(pmenu, "Block Palette")); app.update()
    check("Panels > Block Palette collapses the palette (strip glyph follows)",
          pm.is_visible("palette") is False and app.palette_strip_glyph.cget("text") == "\u25b8")
    m3 = app.build_workspace_menu((0, 0))
    check("checkbutton shows palette off next time", m3._vars[0].get() is False)
    sub(m3, labels(m3)[-1]).invoke(0); app.update()
    check("Panels > Block Palette re-expands it", pm.is_visible("palette") is True)

    pmenu.invoke(idx(pmenu, "Generated Code")); app.update()
    check("Panels > Generated Code hides the code panel", pm.is_visible("code") is False)
    app.refresh_workspace(); app.update()
    check("a refresh does NOT resurrect a user-hidden code panel", pm.is_visible("code") is False)
    app.switch_to_file_view(); app.update()
    app.view_mode = "node"; app.update_right_panel_visibility(); app.update()
    check("layer round-trip keeps it hidden", pm.is_visible("code") is False)
    m4 = app.build_workspace_menu((0, 0))
    check("menu checkbutton shows code off", m4._vars[1].get() is False)
    app.toggle_code_panel(); app.update()
    check("toggle brings it back", pm.is_visible("code") is True)

    # ---------- Nodes layer ----------
    app.switch_to_file_view(); app.update()
    app.file_view_code_mode = False
    check("at Nodes layer", app.view_mode == "file")
    mn = app.build_workspace_menu((300, 150))
    Ln = labels(mn)
    check("Nodes layer: Add node + Add category, then Panels",
          Ln[0].endswith("Add node") and Ln[1].endswith("Add category") and Ln[2] == "-" and Ln[3].endswith("Panels"))
    check("Nodes layer Panels has only the palette (no code panel here)",
          labels(sub(mn, Ln[3])) == ["Block Palette"])

    names = iter(["Alpha", "Beta", "Gamma", "Delta"])
    real_ask = ui.simpledialog.askstring
    ui.simpledialog.askstring = lambda *a, **k: next(names)
    try:
        n_before = len(tab["nodes"])
        mn.invoke(0)   # Add node at (300,150)
        app.update()
        new = tab["nodes"][-1]
        check("node created with the given name", new["name"] == "Alpha" and len(tab["nodes"]) == n_before + 1)
        check("node placed at the cursor position", (new["canvas_x"], new["canvas_y"]) == (300, 150))
        check("stays on the Nodes layer (not opened)", app.view_mode == "file")
        check("a box for it is actually drawn", any(True for _ in app.workspace_canvas.find_withtag("fileview")))

        mn.invoke(1)   # Add category
        app.update()
        cat = tab["nodes"][-1]
        check("category created, kind=category, placed at cursor",
              cat["name"] == "Beta" and cat.get("kind") == "category"
              and (cat["canvas_x"], cat["canvas_y"]) == (300, 150))
        check("category creation stays on the canvas", app.view_mode == "file")

        # Adversarial: negative/odd coordinates are clamped by the handler
        class E: pass
        e = E(); e.x_root = app.workspace_canvas.winfo_rootx() - 40
        e.y_root = app.workspace_canvas.winfo_rooty() - 40
        captured = {}
        orig_popup = tk.Menu.tk_popup
        tk.Menu.tk_popup = lambda self_, x, y: captured.update(menu=self_, x=x, y=y)
        try:
            app._on_workspace_right_click(e)
        finally:
            tk.Menu.tk_popup = orig_popup
        check("right-click handler pops a menu at the click position",
              captured.get("menu") is not None and captured["x"] == e.x_root)
        captured["menu"].invoke(0); app.update()
        n3 = tab["nodes"][-1]
        check("click left/above the canvas clamps to >= 0",
              n3["name"] == "Gamma" and n3["canvas_x"] >= 0 and n3["canvas_y"] >= 0)

        # Cancelling the dialog creates nothing
        ui.simpledialog.askstring = lambda *a, **k: None
        n_now = len(tab["nodes"])
        mn.invoke(0); app.update()
        check("cancelled dialog adds nothing", len(tab["nodes"]) == n_now)

        # Inside a category: new node lands in child_nodes at the cursor
        ui.simpledialog.askstring = lambda *a, **k: "Inner"
        app.open_node(cat["id"]); app.update()
        mi = app.build_workspace_menu((40, 60))
        mi.invoke(0); app.update()
        inner = [n for n in cat["child_nodes"] if n["name"] == "Inner"]
        check("inside a category, right-click node goes into that category at the cursor",
              len(inner) == 1 and (inner[0]["canvas_x"], inner[0]["canvas_y"]) == (40, 60)
              and app.view_mode == "file")
        check("...and not into the top level", not any(n["name"] == "Inner" for n in tab["nodes"]))
    finally:
        ui.simpledialog.askstring = real_ask

    # ---------- Nodes layer code view: no add entries ----------
    app.file_view_code_mode = True
    mc = app.build_workspace_menu((0, 0))
    check("Nodes code view: only Panels (no adding into a text view)",
          labels(mc) == [labels(mc)[0]] and labels(mc)[0].endswith("Panels"))
    app.file_view_code_mode = False

    # ---------- Files layer ----------
    app.switch_to_files_view(); app.update()
    app.files_view_code_mode = False
    mf = app.build_workspace_menu((500, 260))
    Lf = labels(mf)
    check("Files layer: 'New file' top entry", Lf[0].endswith("New file") and Lf[2].endswith("Panels"))
    tabs_before, active_before = len(app.tabs), app.active_tab_index
    mf.invoke(0); app.update()
    nt = app.tabs[-1]
    check("a new tab was added", len(app.tabs) == tabs_before + 1)
    check("new file placed at the cursor", (nt["canvas_x"], nt["canvas_y"]) == (500, 260))
    check("active tab unchanged, still on Files layer",
          app.active_tab_index == active_before and app.view_mode == "files")
    def all_text(w):
        out = []
        for c in w.winfo_children():
            try: out.append(str(c.cget("text")))
            except tk.TclError: pass
            out += all_text(c)
        return out
    strip = " | ".join(all_text(app.tab_bar_frame))
    check("tab strip shows the workspace, not each file", app.workspaces[app.active_ws_index]["title"] in strip and nt["title"] not in strip)
    check("Files box drawn for every tab", len(app._filesview_boxes) == len(app.tabs))
    app.files_view_code_mode = True
    check("Files code view: only Panels",
          labels(app.build_workspace_menu((0, 0)))[0].endswith("Panels"))
    app.files_view_code_mode = False

    # regular new_tab still switches (toolbar + button behaviour unchanged)
    app.new_tab(); app.update()
    check("new_tab() still switches to the new tab", app.active_tab_index == len(app.tabs) - 1)

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All context-menu tests passed.")

main()
