"""
Scripted UI test (run under Xvfb): the designer's camera. The wheel zooms
around the pointer, dragging empty space (or the middle button, or Space) pans,
Fit and 100% reset it, and picking widgets still works while zoomed.
"""
import os
import sys
from types import SimpleNamespace
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_node
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(3):
        app.update_idletasks()
        app.update()


def ev(x, y, **kw):
    return SimpleNamespace(x=x, y=y, num=kw.get("num", "??"), delta=kw.get("delta", 0))


def main():
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.ask_ui_pack = lambda packs: packs[0]
    app.geometry("1400x900")
    try:
        settle(app)
        node = app.create_starter_node("ui", (80, 80))
        app.open_node(node["id"])
        settle(app)
        ed = app.designer_editor
        ed._dz_add_type("button")
        settle(app)
        wid = ed.state["sel"]

        check("starts fitted", ed.state.get("view") is None and ed._dz_scale <= 1.0)
        fit_scale = ed._dz_scale

        # zoom in around a point: the paper point under it stays put
        anchor = (300, 200)
        before = ed._dz_paper_point(ev(*anchor))
        ed._dz_paper_wheel(ev(*anchor, num=4))
        ed._dz_paper_wheel(ev(*anchor, num=4))
        after = ed._dz_paper_point(ev(*anchor))
        check("wheel up zooms in", ed._dz_scale > fit_scale)
        check("the point under the pointer stays put", abs(before[0] - after[0]) < 0.5 and abs(before[1] - after[1]) < 0.5)
        check("the zoom is remembered as a manual view", ed.state["view"] is not None)
        check("the % label follows", ed._dz_zoom_label.cget("text") == f"{round(ed._dz_scale * 100)}%")
        for _ in range(60):
            ed._dz_paper_wheel(ev(*anchor, num=4))
        check("zoom stops at the maximum", abs(ed._dz_scale - 4.0) < 1e-6)
        for _ in range(200):
            ed._dz_paper_wheel(ev(*anchor, num=5))
        check("zoom stops at the minimum", abs(ed._dz_scale - 0.2) < 1e-6)

        # pick a widget while zoomed: the hit test follows the camera
        ed._dz_zoom_reset()
        settle(app)
        box = ed._dz_box(wid)
        s, (ox, oy) = ed._dz_scale, ed._dz_origin
        cx, cy = ox + (box["x"] + box["w"] / 2) * s, oy + (box["y"] + box["h"] / 2) * s
        ed.state["sel"] = None
        ed._dz_paper_press(ev(cx, cy))
        ed._dz_paper_release(ev(cx, cy))
        check("clicking the widget selects it at 100%", ed.state["sel"] == wid)

        # pan: dragging empty space moves the view and keeps the selection
        ed._dz_set_view(0.3, (20, 20))                  # a small paper in the corner: the rest is empty space
        settle(app)
        origin0 = ed._dz_origin
        far = (ed._dz_canvas.winfo_width() - 5, ed._dz_canvas.winfo_height() - 5)     # outside the paper
        ed._dz_paper_press(ev(*far))
        check("pressing empty space starts a pan, not a widget drag", ed._dz_pan is not None and ed._dz_drag is None)
        ed._dz_paper_drag(ev(far[0] - 40, far[1] - 25))
        ed._dz_paper_release(ev(far[0] - 40, far[1] - 25))
        check("the view moved with the drag", abs((origin0[0] - ed._dz_origin[0]) - 40) < 1 and abs((origin0[1] - ed._dz_origin[1]) - 25) < 1)
        check("a pan does not deselect", ed.state["sel"] == wid)
        check("a pan never changes the design", len(ui_node.load_tree(node, app.ui_pack_for("python")).root["children"]) == 1)

        # a plain click on empty space deselects
        ed._dz_paper_press(ev(*far))
        ed._dz_paper_release(ev(*far))
        check("a click on empty space deselects", ed.state["sel"] is None)

        # the paper can't be dragged out of sight
        ed._dz_pan_press(ev(100, 100))
        ed._dz_pan_motion(ev(100 + 50000, 100 + 50000))
        ed._dz_pan_release(ev(100, 100))
        cw = ed._dz_canvas.winfo_width()
        check("some paper always stays on screen", ed._dz_origin[0] <= cw - 1)

        # Space + left drag pans even over a widget
        ed._dz_set_space(True)
        ed._dz_paper_press(ev(cx, cy))
        check("Space + press pans", ed._dz_pan is not None)
        ed._dz_paper_release(ev(cx, cy))
        ed._dz_set_space(False)

        # Fit puts it back
        ed._dz_fit()
        settle(app)
        check("Fit resets the camera", ed.state.get("view") is None and abs(ed._dz_scale - fit_scale) < 1e-6)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
