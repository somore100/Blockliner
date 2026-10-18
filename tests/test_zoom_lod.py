"""Zoom: the zoomed-out look (setting lod_mode: details / names / gray, older
lod_hide_details still honoured), boxes keep their size relative to the zoom,
zooming resizes the live boxes in place (no rebuild, no stand-ins), a look
change rebuilds without leaving old widgets behind. Headless (Xvfb)."""
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
    check("no lod_mode in the defaults (old checkbox stays in charge)", "lod_mode" not in app.settings)

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

    # ---- fast zoom: the live boxes are resized in place, never swapped/rebuilt
    app.set_zoom(1.0); app.update(); app.update()
    n_hooks = len(app._zoom_hooks)      # fresh render (came from the compact look)
    c = app.workspace_canvas
    wins = list(c.find_withtag("node_box"))
    boxes = {n: app._fileview_boxes[n][1] for n in ("verify", "gen_pw", "ui")}
    w0 = boxes["verify"].winfo_width()
    app.zoom_step(-1, 300, 200); app.zoom_step(-1, 300, 200); app.update()
    check("no stand-in rectangles any more", not c.find_withtag("zoom_proxy"))
    check("boxes never hidden while zooming", all(c.itemcget(w, "state") != "hidden" for w in wins))
    check("same canvas window items after zooming", sorted(c.find_withtag("node_box")) == sorted(wins))
    check("same box widgets after zooming", all(app._fileview_boxes[n][1] is b for n, b in boxes.items()))
    check("zoom ended on a zoomed-in step", app.canvas_zoom > 1.0)
    check("box grew with the zoom", boxes["verify"].winfo_width() > w0 * 1.1)
    check("box still shows its details", any("Open" in t for t in texts(boxes["verify"])))
    f = boxes["verify"].winfo_children()[0].winfo_children()[0].cget("font")
    import tkinter.font as tkfont
    check("header font is a shared font sized for the zoom",
          int(tkfont.nametofont(f).cget("size")) == max(5, round(10 * app.canvas_zoom)))
    hdr = boxes["verify"].winfo_children()[0]
    check("header width follows the zoom", int(hdr.cget("width")) == app._zi(215))
    pads = [w.pack_info().get("padx") for w in hdr.winfo_children() if w.winfo_manager() == "pack"]
    check("paddings follow the zoom", any(str(app._zi(8)) in str(p) for p in pads))
    wx = c.coords(app._fileview_boxes["verify"][0])[0]
    node = find_node_by_id(app.tabs[0]["nodes"], "verify")
    check("box position follows the zoom", abs(wx - node["canvas_x"] * app.canvas_zoom) < 1)
    check("wires redrawn once, no duplicates",
          len(c.find_withtag("wire")) == len(set(c.find_withtag("wire"))))
    check("zoom hooks do not pile up on resize", n_hooks > 10 and len(app._zoom_hooks) == n_hooks)

    # ---- no in-between frame: when the resize forces its screen update, the
    # view is already scrolled to its final place (else the box is drawn
    # resized-but-not-moved for a frame = the stutter seen when zooming fast)
    snaps = []
    orig_ui = app.update_idletasks
    def spy():
        if not snaps:
            win = app._fileview_boxes["verify"][0]
            snaps.append((c.canvasx(0), c.canvasy(0), tuple(c.coords(win)),
                          len(c.find_withtag("grid")), app.canvas_zoom))
        orig_ui()
    app.update_idletasks = spy
    for _ in range(3): app.zoom_step(-1, 500, 300)
    app.update()
    app.update_idletasks = orig_ui
    final = (c.canvasx(0), c.canvasy(0), tuple(c.coords(app._fileview_boxes["verify"][0])))
    check("first screen update already has the final view origin",
          bool(snaps) and abs(snaps[0][0] - final[0]) < 1 and abs(snaps[0][1] - final[1]) < 1)
    check("...and the box already at its final place", bool(snaps) and snaps[0][2] == final[2])
    check("...and the grid already drawn for the new zoom", bool(snaps) and snaps[0][3] > 0)
    gsnap = sorted(c.coords(i)[0] for i in c.find_withtag("grid") if c.type(i) == "line")[:3]
    app.redraw_grid()
    check("grid drawn before the update equals the final grid",
          gsnap == sorted(c.coords(i)[0] for i in c.find_withtag("grid") if c.type(i) == "line")[:3])
    boxes = {n: app._fileview_boxes[n][1] for n in ("verify", "gen_pw", "ui")}

    # ---- crossing into the names-only look: ONE rebuild, old widgets destroyed
    old = list(boxes.values())
    app.set_zoom(0.3); app.update(); app.update()
    check("look change rebuilt the boxes", all(app._fileview_boxes[n][1] is not b for n, b in boxes.items()))
    check("old box widgets are destroyed (no leak)", not any(b.winfo_exists() for b in old))
    check("no leftover old canvas items", not c.find_withtag("fileview_old"))
    check("exactly three boxes on the canvas", len(c.find_withtag("node_box")) == 3)

    # ---- the three zoomed-out looks
    check("lod_mode default = names", canvas_view.lod_mode({}) == "names")
    check("old checkbox off = details", canvas_view.lod_mode({"lod_hide_details": False}) == "details")
    check("old checkbox on = names", canvas_view.lod_mode({"lod_hide_details": True}) == "names")
    check("lod_mode wins over the old checkbox",
          canvas_view.lod_mode({"lod_mode": "gray", "lod_hide_details": False}) == "gray")
    check("garbage lod_mode = names", canvas_view.lod_mode({"lod_mode": "x"}) == "names" and
          canvas_view.lod_mode(None) == "names")
    check("box_look: zoomed in is always full",
          all(canvas_view.box_look(1.0, m) == "full" for m in canvas_view.LOD_MODES))
    check("box_look: details mode is full when zoomed out", canvas_view.box_look(0.3, "details") == "full")
    check("box_look: names / gray when zoomed out",
          canvas_view.box_look(0.3, "names") == "names" and canvas_view.box_look(0.3, "gray") == "gray")

    app.settings["lod_mode"] = "gray"
    app.apply_zoom(); app.update(); app.update()
    gb = app._fileview_boxes["verify"][1]
    check("gray look: no text at all", [t for t in texts(gb) if t] == [])
    check("gray look: grey header", gb.winfo_children()[0].cget("bg") == "#5a5a5a")
    rw, rh = gb.winfo_reqwidth() / app.canvas_zoom, gb.winfo_reqheight() / app.canvas_zoom   # may be scrolled off-screen
    check("gray look: same compact size as names", 190 <= rw <= 260 and rh <= 70)
    check("gray look: header still drags", bool(gb.winfo_children()[0].bind("<ButtonPress-1>")))

    app.settings["lod_mode"] = "details"
    app.apply_zoom(); app.update(); app.update()
    check("details look: full box when zoomed out", any("Open" in t for t in texts(app._fileview_boxes["verify"][1])))
    app.settings["lod_mode"] = "names"
    app.apply_zoom(); app.update(); app.update()
    check("names look again: title only", len(texts(app._fileview_boxes["verify"][1])) == 1)

    # ---- zooming inside the compact look resizes in place too
    b = app._fileview_boxes["verify"][1]
    app.zoom_step(1, 300, 200); app.update()
    check("compact boxes also resize in place", app._fileview_boxes["verify"][1] is b)
    check("compact box keeps ~215 model units", 190 <= size(app, "verify")[0] <= 260)

    # ---- full refresh destroys the old boxes too (they used to pile up)
    app.set_zoom(1.0); app.update()
    old = [b for _w, b in app._fileview_boxes.values()]
    app.refresh_workspace(); app.update(); app.update()
    check("refresh_workspace destroys the old box widgets", not any(b.winfo_exists() for b in old))
    kids = [w for w in c.winfo_children() if isinstance(w, tk.Frame)]
    check("no stray box frames left on the canvas", len(kids) <= 3 + 1)

    # ---- Files layer: same in-place resize
    app.goto_layer("files") if hasattr(app, "goto_layer") else None
    app.update(); app.update()
    if app.view_mode == "files":
        fb = {i: b for i, (_w, b) in app._filesview_boxes.items()}
        app.zoom_step(-1, 300, 200); app.update()
        check("Files layer: same widgets after zoom", all(app._filesview_boxes[i][1] is b for i, b in fb.items()))
        app.settings["lod_mode"] = "gray"; app.set_zoom(0.3); app.update(); app.update()
        check("Files layer gray look: no text", all([t for t in texts(b) if t] == [] for _w, b in app._filesview_boxes.values()))
        app.settings["lod_mode"] = "names"; app.set_zoom(1.0); app.update()
    else:
        check("could switch to the Files layer", False)

    # ---- Settings dialog: the 3-way choice saves and applies at once
    from tkinter import ttk
    def walk(w):
        for ch in w.winfo_children():
            yield ch
            yield from walk(ch)
    app.goto_layer("nodes") if hasattr(app, "goto_layer") else app.switch_to_file_view()
    app.update()
    app.settings.pop("lod_mode", None); app.settings["lod_hide_details"] = True
    app.set_zoom(0.3); app.update()
    before = set(app.winfo_children())
    app.settings_dialog(); app.update()
    dlg = [w for w in app.winfo_children() if w not in before and isinstance(w, tk.Toplevel)][-1]
    labels = dict(canvas_view.LOD_MODE_CHOICES)
    combo = [w for w in walk(dlg) if isinstance(w, ttk.Combobox) and labels["gray"] in w.cget("values")]
    check("Settings has the zoomed-out look choice", len(combo) == 1)
    check("it starts on the current look (names)", combo and combo[0].get() == labels["names"])
    combo[0].set(labels["gray"])
    save = [w for w in walk(dlg) if isinstance(w, tk.Button) and "Save" in str(w.cget("text"))]
    save[0].invoke(); app.update(); app.update()
    check("saved as lod_mode = gray", app.settings.get("lod_mode") == "gray")
    check("old checkbox kept in step (gray hides details)", app.settings.get("lod_hide_details") is True)
    check("new look applied at once, no extra zoom needed",
          app.view_mode == "file" and all([t for t in texts(b) if t] == [] for _w, b in app._fileview_boxes.values()))
    app.settings["lod_mode"] = "names"

    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
