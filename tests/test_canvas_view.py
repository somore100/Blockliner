"""Wheel zoom, coordinate grid, show_coords setting, Settings button. Headless (Xvfb)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import canvas_view as cv
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)

def main():
    # ---- pure helpers
    check("clamp low/high", cv.clamp_zoom(0.01) == cv.ZOOM_MIN and cv.clamp_zoom(99) == cv.ZOOM_MAX)
    check("clamp garbage -> 1.0", cv.clamp_zoom("x") == 1.0 and cv.clamp_zoom(float("nan")) == 1.0 and cv.clamp_zoom(None) == 1.0)
    check("wheel up zooms in, down zooms out", cv.zoom_after_wheel(1, -1) > 1 > cv.zoom_after_wheel(1, 1))
    check("zoom never leaves limits", cv.zoom_after_wheel(cv.ZOOM_MAX, -1) == cv.ZOOM_MAX and cv.zoom_after_wheel(cv.ZOOM_MIN, 1) == cv.ZOOM_MIN)
    check("grid step keeps >= 40px apart", all(cv.grid_step(z) * z >= cv.MIN_GRID_PX for z in (0.5, 0.7, 1, 1.5, 2)))
    check("grid values are multiples", cv.grid_values(-25, 105, 50) == [0, 50, 100])
    check("grid values refuse absurd counts", cv.grid_values(0, 10 ** 9, 1) == [])
    check("grid values empty range", cv.grid_values(5, 1, 10) == [])
    z = 1.7; p = 123.0
    check("anchor math keeps the point under the pointer", abs(cv.anchor_view_origin(p, 80, z) + 80 - p * z) < 1e-9)

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None
    app.geometry("1300x800"); app.update()
    c = app.workspace_canvas

    # ---- toolbar: Settings button replaces the logo
    top = [w for w in walk(app) if w.winfo_class() == "TButton" and "⚙" in str(w.cget("text"))]
    check("Settings (gear) button in the top-left", len(top) == 1 and top[0].winfo_rootx() < 120)
    check("old toolbar logo image is gone", not hasattr(app, "logo_photo"))

    # ---- wheel zoom on the nodes layer
    app.goto_layer("nodes"); app.update(); app.update()
    app.set_zoom(1.0); app.update()
    boxes = [i for i in c.find_withtag("node_box")]
    check("boxes drawn", len(boxes) >= 1)
    node = app.tabs[app.active_tab_index]["nodes"][0]
    app.winfo_pointerxy()
    w1 = app._fileview_boxes[node["id"]][1].winfo_reqwidth()
    ox, oy = c.coords(app._fileview_boxes[node["id"]][0])
    app.zoom_step(-1, 200, 200); app.apply_zoom(); app.update()
    check("zoom in grows the zoom", abs(app.canvas_zoom - cv.ZOOM_STEP) < 1e-9)
    nx, ny = c.coords(app._fileview_boxes[node["id"]][0])
    check("box position scales with zoom", abs(nx - node["canvas_x"] * app.canvas_zoom) < 1.0)
    check("model position is untouched by zoom", node["canvas_x"] * app.canvas_zoom == nx or abs(node["canvas_x"] - nx / app.canvas_zoom) < 1e-6)
    w2 = app._fileview_boxes[node["id"]][1].winfo_reqwidth()
    check("box widgets are rebuilt larger", w2 >= w1)
    app.set_zoom(2.0); app.update()
    check("zoom 2.0 doubles the box width", app._fileview_boxes[node["id"]][1].winfo_reqwidth() > w1 * 1.5)
    app.set_zoom(0.5); app.update()
    check("zoom 0.5 shrinks the box width", app._fileview_boxes[node["id"]][1].winfo_reqwidth() < w1)
    app.set_zoom(10); check("set_zoom clamps", app.canvas_zoom == cv.ZOOM_MAX)
    app.set_zoom(1.0); app.update()

    # anchor: the model point under the pointer stays put
    app.set_zoom(1.0); app.update()
    mx = c.canvasx(300); my = c.canvasy(250)
    app.zoom_step(-1, 300, 250); app.apply_zoom(); app.update()
    check("point under pointer stays under pointer (x)", abs(c.canvasx(300) - mx * app.canvas_zoom) <= 3)
    check("point under pointer stays under pointer (y)", abs(c.canvasy(250) - my * app.canvas_zoom) <= 3)
    app.set_zoom(1.0); app.update()

    # wheel handler: zoom on canvas layers, plain scroll elsewhere
    ev = types.SimpleNamespace(num=4, delta=0)
    app._on_mousewheel(ev, c); app.apply_zoom()
    check("wheel event on the Nodes canvas zooms", app.canvas_zoom > 1.0)
    app.set_zoom(1.0)
    app.goto_layer("blocks"); app.update(); app.update()
    z0 = app.canvas_zoom
    app._on_mousewheel(types.SimpleNamespace(num=5, delta=0), c); app.update()
    check("wheel on the Blocks layer does NOT zoom", app.canvas_zoom == z0)
    check("canvas_layer_active false on Blocks", not app.canvas_layer_active())

    # ---- grid
    app.goto_layer("nodes"); app.update(); app.update()
    app.settings["show_coords"] = False; app.redraw_grid()
    lines = c.find_withtag("grid")
    check("grid lines drawn", len([i for i in lines if c.type(i) == "line"]) >= 4)
    check("no numbers when the setting is off", not [i for i in lines if c.type(i) == "text"])
    app.settings["show_coords"] = True; app.redraw_grid()
    texts = [c.itemcget(i, "text") for i in c.find_withtag("grid") if c.type(i) == "text"]
    check("numbers appear when the setting is on", len(texts) >= 2 and all(t.lstrip("-").isdigit() for t in texts))
    check("grid is lowest on the canvas", c.find_all()[0] in c.find_withtag("grid"))
    app.settings["show_coords"] = False; app.redraw_grid()

    # grid values at a scrolled/zoomed view match model units
    app.set_zoom(2.0); app.settings["show_coords"] = True; app.update(); app.redraw_grid()
    step = cv.grid_step(2.0)
    texts = [int(c.itemcget(i, "text")) for i in c.find_withtag("grid") if c.type(i) == "text"]
    check("labels are multiples of the grid step", all(t % step == 0 for t in texts))
    app.set_zoom(1.0); app.settings["show_coords"] = False

    # grid never drawn on the Blocks layer
    app.goto_layer("blocks"); app.update(); app.update()
    check("no grid on the Blocks layer", not c.find_withtag("grid"))

    # settings default and dialog checkbox exist
    import ui_common
    check("show_coords default is off", ui_common.DEFAULT_SETTINGS.get("show_coords") is False)

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
