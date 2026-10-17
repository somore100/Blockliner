"""Zoom: compact boxes when zoomed far out (setting lod_hide_details), boxes keep
their size relative to the zoom, and fast zooming previews with cheap rectangles
instead of live widgets. Headless (Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI
import canvas_view

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def fn(name, params, ret):
    return make_node(name, node_id=name, blocks=[("func_def", {"name": name, "params": params,
            "_children": [("return_statement", {"value": ret})]})])

def texts(w):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, (tk.Label, tk.Button)): out.append(str(ch.cget("text")))
        out += texts(ch)
    return out

def build():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = [fn("verify", "username, password", "approved, declined"), fn("gen_pw", "", "text"),
             make_node("ui", node_id="ui", blocks=[("print_output", {"value": "'hi'"})])]
    for i, n in enumerate(nodes): n["canvas_x"], n["canvas_y"] = 20 + i * 300, 40
    tab["nodes"] = nodes; tab["active_node_id"] = "ui"; tab["file_view_path"] = []
    app.project_blocks = find_node_by_id(nodes, "ui")["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update(); app.update()
    return app

def size(app, nid):
    w = app._fileview_boxes[nid][1]; return w.winfo_width() / app.canvas_zoom, w.winfo_height() / app.canvas_zoom

def main():
    # ---- pure helper
    check("compact below the threshold", canvas_view.compact_at(0.3) and not canvas_view.compact_at(1.0))
    check("setting off = never compact", not canvas_view.compact_at(0.2, False))
    check("threshold itself is not compact", not canvas_view.compact_at(canvas_view.LOD_ZOOM))
    check("garbage zoom does not crash", canvas_view.compact_at("x") is False)

    app = build()
    check("setting defaults to on", app.settings.get("lod_hide_details") is True)

    # ---- normal box shows its details
    full = texts(app._fileview_boxes["verify"][1])
    check("zoom 1.0 box shows ports, id and Open button", any("Open" in t for t in full) and any("id verify" in t for t in full) and "username" in full)

    # ---- compact when zoomed out
    app.set_zoom(0.3); app.update(); app.update()
    small = texts(app._fileview_boxes["verify"][1])
    check("zoomed out box shows only its title", len(small) == 1 and "verify" in small[0])
    sizes = [size(app, n) for n in ("verify", "gen_pw", "ui")]
    check("compact boxes all the same size (title strip)", len(set(sizes)) == 1)
    check("compact box stays near 215 model units wide (was ~500)", 190 <= sizes[0][0] <= 260)
    check("compact box is short", sizes[0][1] <= 70)

    # ---- right at the edge: details come back
    app.set_zoom(0.6); app.update(); app.update()
    check("at 0.6 details are back", any("Open" in t for t in texts(app._fileview_boxes["verify"][1])))

    # ---- setting off: always full boxes
    app.settings["lod_hide_details"] = False
    app.set_zoom(0.3); app.update(); app.update()
    check("setting off keeps full boxes when zoomed out", any("Open" in t for t in texts(app._fileview_boxes["verify"][1])))
    app.settings["lod_hide_details"] = True

    # ---- headers still drag-able in compact mode: header + name label are bound
    app.set_zoom(0.3); app.update(); app.update()
    box = app._fileview_boxes["verify"][1]
    header = box.winfo_children()[0]
    check("compact header keeps its drag binding", bool(header.bind("<ButtonPress-1>")))

    # ---- fast zoom: live widgets are swapped for cheap rectangles, then restored
    app.set_zoom(1.0); app.update(); app.update()
    c = app.workspace_canvas
    wins = list(c.find_withtag("node_box"))
    app.zoom_step(-1, 300, 200)
    proxies = c.find_withtag("zoom_proxy")
    check("zoom preview draws proxy rectangles", len(c.find_withtag("zoom_proxy_text")) == 3 and len(proxies) >= 6)
    check("live widgets hidden during the preview", all(c.itemcget(w, "state") == "hidden" for w in wins))
    n_after_first = len(c.find_withtag("zoom_proxy"))
    app.zoom_step(-1, 300, 200)
    check("further wheel steps do not pile up more proxies", len(c.find_withtag("zoom_proxy")) == n_after_first)
    app.after(400, lambda: None); app.update()
    for _ in range(10):
        app.update(); app.after(60)   # let the settle timer fire
        if not c.find_withtag("zoom_proxy"): break
    app.apply_zoom(); app.update()
    check("proxies are gone after the settle re-render", not c.find_withtag("zoom_proxy"))
    check("real boxes are shown again", len(c.find_withtag("node_box")) == 3 and
          all(c.itemcget(w, "state") != "hidden" for w in c.find_withtag("node_box")))
    check("zoom ended on a zoomed-in step", app.canvas_zoom > 1.0)

    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
