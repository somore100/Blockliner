"""Scripted UI test (run under Xvfb): a Nodes-layer box looks like a Files-layer box (a thin ring, not a thick band),
its resize strips follow the ring colour, and dragging an edge still resizes the node."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI
from ui_canvas import NodeBox

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0")
    try:
        settle(app)
        app.goto_layer("nodes")
        settle(app)
        boxes = [w for w in app.workspace_canvas.winfo_children() if isinstance(w, NodeBox)]
        check("the Nodes layer draws NodeBoxes", len(boxes) >= 1)
        box = boxes[0]
        check("each box has its four strips", len(box._strips) == 4)
        edge = app.RESIZE_EDGE
        check("the strips are no thicker than the ring plus one pixel",
              edge <= int(str(box.cget("highlightthickness"))) + 1)
        check("the strips start in the ring colour", all(s.cget("bg") == box.cget("highlightbackground")
                                                          for s in box._strips))
        box.configure(highlightbackground="#ff3b3b")
        check("and follow the ring when it changes", all(s.cget("bg") == "#ff3b3b" for s in box._strips))
        box["highlightbackground"] = "#112233"
        check("also when set by item assignment", all(s.cget("bg") == "#112233" for s in box._strips))

        node = app.tabs[app.active_tab_index]["nodes"][0]
        w0 = box.winfo_width()
        east = box._strips[3]
        x = east.winfo_rootx() + 1
        y = east.winfo_rooty() + east.winfo_height() // 2
        east.event_generate("<ButtonPress-1>", x=1, y=5, rootx=x, rooty=y)
        east.event_generate("<B1-Motion>", x=1, y=5, rootx=x + 60, rooty=y)
        east.event_generate("<ButtonRelease-1>", x=1, y=5, rootx=x + 60, rooty=y)
        settle(app, 0.5)
        check("dragging the east strip widens the node", (node.get("canvas_w") or 0) > 0 and
              [w for w in app.workspace_canvas.winfo_children() if isinstance(w, NodeBox)][0].winfo_width() > w0)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
