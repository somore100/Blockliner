"""Scripted UI test (run under Xvfb): turning the wheel shows exact-size stand-ins instead of resizing every real
box on every notch; they are replaced by the real boxes once the wheel is still; the point under the pointer stays put."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canvas_view import PREVIEW_MIN_BOXES, ZOOM_SETTLE_MS, use_zoom_preview
from nodes_model import make_node
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.0):
    end = time.time() + seconds
    while True:
        app.update_idletasks()
        app.update()
        if time.time() >= end:
            break
        time.sleep(0.01)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]
        nodes = []
        for i in range(40):
            n = make_node(f"node_{i}", node_id=f"n{i}", order=i, blocks=[("print_output", {"value": f"'{i}'"})])
            n["canvas_x"], n["canvas_y"] = (i % 8) * 300, (i // 8) * 170
            nodes.append(n)
        nodes[1]["blocks"].append(("func_call", {"name": "node_0", "args": ""}))
        tab["nodes"][:] = nodes
        tab["active_node_id"] = "n0"
        app.goto_layer("nodes")
        settle(app, 0.3)
        c = app.workspace_canvas
        wins = {nid: w for nid, (w, _b) in app._fileview_boxes.items()}
        check("40 boxes on the Nodes layer", len(wins) == 40)

        # the rule: automatic = stand-ins from PREVIEW_MIN_BOXES boxes; the setting can force either way
        check("auto: few boxes resize live, many use stand-ins",
              not use_zoom_preview({}, PREVIEW_MIN_BOXES - 1) and use_zoom_preview({}, PREVIEW_MIN_BOXES))
        check("the setting forces live or fast; junk means auto",
              not use_zoom_preview({"zoom_style": "live"}, 500) and use_zoom_preview({"zoom_style": "fast"}, 1)
              and use_zoom_preview({"zoom_style": "nope"}, 500) and not use_zoom_preview({"zoom_style": "nope"}, 3))
        app.settings["zoom_style"] = "live"
        app.zoom_step(-1, 400, 300)
        check("live: no stand-ins even with 40 boxes", app._zprev is None and not c.find_withtag("zprev"))
        settle(app, 0.3)
        check("live: the real boxes were resized on the next idle", abs(app._rendered_zoom - app.canvas_zoom) < 1e-9)
        app.set_zoom(1.0)
        settle(app, 0.2)
        app.settings["zoom_style"] = "auto"

        # pointer anchor: the model point under (400, 300) before
        z0 = app.canvas_zoom
        before = (c.canvasx(400) / z0, c.canvasy(300) / z0)
        app.zoom_step(-1, 400, 300)
        settle(app)
        check("a wheel notch shows stand-ins", app._zprev is not None and len(c.find_withtag("zprev")) == 3 * 40)
        check("the real boxes are hidden meanwhile", all(c.itemcget(w, "state") == "hidden" for w in wins.values()))
        z1 = app.canvas_zoom
        e = app._zprev["entries"][0]
        x0, y0, x1, y1 = c.coords(e["frame"])
        check("stand-ins are exactly model size x zoom", abs((x1 - x0) - e["w"] * z1) < 0.01 and abs((y1 - y0) - e["h"] * z1) < 0.01 and abs(x0 - e["x"] * z1) < 0.01)
        for _ in range(6):
            app.zoom_step(-1, 400, 300)
        settle(app)
        zb = app.canvas_zoom
        mid = (c.canvasx(400) / zb, c.canvasy(300) / zb)
        check("while turning, the point under the pointer stays put", abs(mid[0] - before[0]) < 1 and abs(mid[1] - before[1]) < 1)
        check("wires follow the scale (a call wire exists)", len(c.find_withtag("wire")) >= 1)

        settle(app, ZOOM_SETTLE_MS / 1000 + 0.5)
        check("when the wheel is still the stand-ins are gone", app._zprev is None and not c.find_withtag("zprev"))
        check("the real boxes are back and visible", all(c.itemcget(w, "state") == "normal" for w in wins.values()))
        check("the real zoom was applied once", abs(app._rendered_zoom - zb) < 1e-9)
        w, _b = app._fileview_boxes["n9"]
        cx, cy = c.coords(w)
        check("boxes sit at model x zoom", abs(cx - nodes[9]["canvas_x"] * zb) < 1 and abs(cy - nodes[9]["canvas_y"] * zb) < 1)
        after = (c.canvasx(400) / zb, c.canvasy(300) / zb)
        check("the pointer point is still the same after the swap", abs(after[0] - before[0]) < 1.5 and abs(after[1] - before[1]) < 1.5)

        # a programmatic zoom in the middle of a burst ends the preview cleanly
        app.zoom_step(1, 400, 300)
        settle(app)
        check("preview is up again", app._zprev is not None)
        app.set_zoom(1.0)
        settle(app, 0.2)
        check("set_zoom ends the preview and applies", app._zprev is None and not c.find_withtag("zprev") and abs(app._rendered_zoom - 1.0) < 1e-9
              and all(c.itemcget(w, "state") == "normal" for w, _b in app._fileview_boxes.values()))

        # leaving the canvas layer mid-burst leaves nothing behind
        app.zoom_step(-1, 400, 300)
        settle(app)
        app.goto_layer("blocks")
        settle(app, ZOOM_SETTLE_MS / 1000 + 0.4)
        check("switching layer mid-zoom leaves no stand-ins", app._zprev is None and not c.find_withtag("zprev"))

        # crossing the zoomed-out look still rebuilds (names-only boxes)
        app.goto_layer("nodes")
        settle(app, 0.3)
        app.set_zoom(0.5)
        settle(app, 0.3)
        check("zoomed far out the boxes are rebuilt compact", app._look_now() != "full" and app._rendered_look == app._look_now() and len(app._fileview_boxes) == 40)

        # the Files layer uses the same stand-ins
        app.goto_layer("files")
        settle(app, 0.3)
        app.set_zoom(1.0)
        settle(app, 0.2)
        app.settings["zoom_style"] = "fast"          # one file: automatic would resize it live
        app.zoom_step(-1, 300, 200)
        settle(app)
        check("the Files layer shows stand-ins too", app._zprev is not None and len(app._zprev["entries"]) == len(app._filesview_boxes))
        settle(app, ZOOM_SETTLE_MS / 1000 + 0.4)
        check("and settles", app._zprev is None)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
