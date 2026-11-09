"""Scripted UI test (run under Xvfb): Ctrl+wheel zooms the Blocks layer, the plain wheel scrolls,
and a setting swaps them."""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI
from ui_widgets import BlockWidget

FAILURES = []
CTRL = 0x4


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.25):
    """Run the event loop for a moment (a zoom redraws 60 ms after the last wheel step)."""
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def first_block_height(app):
    for c in app.workspace_frame.winfo_children():
        if isinstance(c, BlockWidget):
            return c.winfo_reqheight()
    return None


def wheel(app, up, state=0):
    app._on_mousewheel(SimpleNamespace(num=4 if up else 5, delta=0, state=state), app.workspace_canvas)
    settle(app)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900")
    try:
        settle(app)
        app.goto_layer("blocks")
        del app.project_blocks[:]
        app.project_blocks.extend(("comment", {"text": str(i)}) for i in range(40))
        app.refresh_workspace()
        settle(app)
        h0 = first_block_height(app)
        check("starts at 100%", getattr(app, "block_scale", 1.0) == 1.0)

        wheel(app, up=False, state=0)
        check("the plain wheel scrolls and does not zoom", getattr(app, "block_scale", 1.0) == 1.0
              and app.workspace_canvas.yview()[0] > 0)

        app.workspace_canvas.yview_moveto(0.2)
        before = app.workspace_canvas.yview()[0]
        wheel(app, up=True, state=CTRL)
        check("Ctrl+wheel up zooms in", app.block_scale > 1.0)
        check("the blocks were drawn bigger", first_block_height(app) > h0)
        check("the scroll position is kept", abs(app.workspace_canvas.yview()[0] - before) < 0.05)
        for _ in range(6):
            wheel(app, up=True, state=CTRL)
        check("zoom stops at 200%", app.block_scale == 2.0)
        for _ in range(9):
            wheel(app, up=False, state=CTRL)
        check("zoom out stops at 60%", app.block_scale == 0.6 and first_block_height(app) < h0)

        app.settings["block_zoom_wheel"] = "wheel"
        app.block_scale = 1.0
        app.refresh_workspace()
        settle(app)
        wheel(app, up=True, state=0)
        check("swapped: the plain wheel zooms", app.block_scale > 1.0)
        top = app.workspace_canvas.yview()[0]
        wheel(app, up=False, state=CTRL)
        check("swapped: Ctrl+wheel scrolls", app.block_scale > 1.0 and app.workspace_canvas.yview()[0] > top)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
