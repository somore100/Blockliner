"""Desktop-polish fixes (2026-10-11): hidden frame no longer covers the y=0 axis,
clicking the wire-drop menu no longer closes it before its command runs,
wider zoom range, '+ New Group' button. Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import canvas_view as cv
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def button_texts(frame):
    return [w.cget("text") for w in frame.winfo_children() if isinstance(w, tk.Button)]

def main():
    check("zoom range is 0.2 .. 4.0", cv.ZOOM_MIN == 0.2 and cv.ZOOM_MAX == 4.0)
    check("grid stays readable at the new extremes",
          all(cv.grid_step(z) * z >= cv.MIN_GRID_PX for z in (0.2, 0.3, 3, 4)))

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None
    app.maybe_notify = lambda *a, **k: None
    app.geometry("1300x800"); app.update()
    c = app.workspace_canvas
    wid = app.workspace_frame_window_id

    # ---- frame window must not occlude the grid on the canvas layers
    app.goto_layer("nodes"); app.update(); app.update()
    check("nodes layer: frame window hidden", c.itemcget(wid, "state") == "hidden")
    app.goto_layer("files"); app.update(); app.update()
    check("files layer: frame window hidden", c.itemcget(wid, "state") == "hidden")
    app.goto_layer("blocks"); app.update(); app.update()
    check("blocks layer: frame window visible again", c.itemcget(wid, "state") == "normal")
    app.goto_layer("nodes"); app.update(); app.update()
    check("back on nodes: hidden again", c.itemcget(wid, "state") == "hidden")

    # ---- extreme zoom still draws
    for z in (0.2, 4.0):
        app.set_zoom(z); app.update(); app.update()
        check(f"zoom {z} applied and boxes drawn", abs(app.canvas_zoom - z) < 1e-9 and c.find_withtag("node_box"))
    app.set_zoom(1.0); app.update()

    # ---- New Group button on both canvas layers
    check("nodes layer has '+ New Group'", any("New Group" in t for t in button_texts(app.node_nav_frame)))
    tab = app.tabs[app.active_tab_index]
    n0 = len(tab.get("groups", []))
    g = app.add_group_in_view(); app.update()
    check("add_group_in_view creates a group on the file", len(tab["groups"]) == n0 + 1 and g in tab["groups"])
    check("group is placed inside the visible area", 0 <= g["x"] < 300 and 0 <= g["y"] < 300)
    app.goto_layer("files"); app.update(); app.update()
    check("files layer has '+ New Group'", any("New Group" in t for t in button_texts(app.node_nav_frame)))
    ws = app.workspaces[app.active_workspace_index] if hasattr(app, "active_workspace_index") else None
    g2 = app.add_group_in_view(); app.update()
    check("files-layer group created", g2 is not None and g2["id"])
    app.goto_layer("nodes"); app.update()
    app.toggle_file_view_code_mode(); app.update()
    check("no '+ New Group' button in code view", not any("New Group" in t for t in button_texts(app.node_nav_frame)))
    app.toggle_file_view_code_mode(); app.update()

    # ---- click on the drop menu must not dismiss it
    src = tab["nodes"][0]["id"]
    app.show_drop_menu = app.show_drop_menu  # real one
    menu = app.build_drop_menu(src, (100, 100))
    app._drop_menu = menu
    app._on_any_press(types.SimpleNamespace(widget=menu))
    check("click ON the drop menu keeps it", app._drop_menu is menu)
    app._on_any_press(types.SimpleNamespace(widget=c))
    check("click elsewhere dismisses it", app._drop_menu is None)
    app._drop_menu = menu
    app._on_any_press(types.SimpleNamespace())          # fake event with no widget
    check("event without widget dismisses (no crash)", app._drop_menu is None)

    app.destroy()
    print("\nFAILURES:", FAILURES if FAILURES else "none")
    sys.exit(1 if FAILURES else 0)

main()
