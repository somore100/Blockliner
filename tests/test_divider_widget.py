"""Scripted UI test (run under Xvfb): a divider shows as a slim coloured line, can be picked
with other blocks and grouped into a node."""
import os
import sys
from tkinter import messagebox, simpledialog

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI
from ui_common import DIVIDER_COLORS
from ui_widgets import BlockWidget

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(4):
        app.update_idletasks()
        app.update()


def widgets(root):
    out = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, BlockWidget):
                out.append(c)
            walk(c)
    walk(root)
    return out


def main():
    messagebox.showinfo = lambda *a, **k: None
    simpledialog.askstring = lambda *a, **k: "Setup part"
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900")
    try:
        settle(app)
        app.goto_layer("blocks")
        check("the palette knows the divider", "divider" in app.blocks)
        node = app.get_active_node(app.tabs[app.active_tab_index])
        del app.project_blocks[:]
        app.project_blocks.extend([("divider", {"title": "Setup", "color": "pink"}),
                                   ("comment", {"text": "one"}), ("comment", {"text": "two"})])
        app.refresh_workspace()
        settle(app)
        ws = widgets(app.workspace_frame)
        check("three blocks are drawn", len(ws) == 3)
        line = ws[0]
        check("the divider is a slim line, shorter than a normal block header", line.winfo_reqheight() < ws[1].winfo_reqheight())
        header = line.winfo_children()[0]
        check("it takes the chosen colour", str(header.cget("bg")) == DIVIDER_COLORS["pink"])
        app.update_generated_code()
        check("the code gets a comment line for it", "# ---- Setup ----" in app.code_text)

        app.select_block(0, app.project_blocks)
        app.select_block(1, app.project_blocks, state=0x4)
        app.make_node_from_selection()
        settle(app)
        moved = [n for n in app.tabs[app.active_tab_index]["nodes"] if n["name"] == "Setup part"]
        check("a divider can be grouped into a node with other blocks", len(moved) == 1 and moved[0]["blocks"][0][0] == "divider")
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
