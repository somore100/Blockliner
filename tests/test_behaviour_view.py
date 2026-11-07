"""
Scripted UI test (run under Xvfb): the Behaviour view of a UI window. It lists
each linked event with the blocks of the function it runs, edits go to that
function (never to the window's generated code), and Back returns to the designer.
"""
import os
import sys
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_node
from ui import BlocklinerUI
from ui_widgets import BlockWidget, EventRowWidget

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(4):
        app.update_idletasks()
        app.update()


def widgets_of(root, kind):
    out = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, kind):
                out.append(c)
            walk(c)
    walk(root)
    return out


def main():
    messagebox.askyesno = lambda *a, **k: True
    shown = []
    messagebox.showinfo = lambda *a, **k: shown.append(a)
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
        ed._dz_close_inline(commit=False)
        bid = ed.state["sel"]
        name = ed._dz_tree_now().find(bid)["name"]

        # no events yet: the view says so, and the palette has nowhere to add
        ed.port.show_behaviour()
        settle(app)
        check("Behaviour replaces the designer", app.behaviour_active() and app.current_editor() is None)
        check("no rows yet", not widgets_of(app.workspace_frame, EventRowWidget))
        app.add_block_to_workspace(app.blocks["print_output"])
        check("adding with no function explains instead of editing the window", len(shown) == 1)
        check("the window's own code was not touched", not ui_node.is_detached(node))

        # link a function, come back
        app.hide_ui_behaviour()
        settle(app)
        check("Back to design shows the designer again", not app.behaviour_active() and app.current_editor() is not None)
        fid = ed._dz_new_handler(name, "command")
        ed._dz_apply(lambda t: t.set_event(bid, "command", fid))
        settle(app)
        ed.port.show_behaviour()
        settle(app)
        rows = widgets_of(app.workspace_frame, EventRowWidget)
        check("the linked event is listed", len(rows) == 1 and rows[0].row["widget"] == name)
        handler = next(n for n in app.cb.function_nodes() if n["id"] == fid)
        check("its body is the function's own block list", rows[0].body_list is handler["blocks"])
        check("this body is where palette blocks would go", app.behaviour_target_list() is handler["blocks"])

        # an edit made through the view lands in the function
        handler["blocks"].append(("print_output", {"value": '"clicked"'}))
        app.refresh_workspace()
        settle(app)
        rows = widgets_of(app.workspace_frame, EventRowWidget)
        check("the function's block shows in the row", len(widgets_of(rows[0], BlockWidget)) >= 1)
        check("the window node is still attached", not ui_node.is_detached(node))

        # opening the function leaves Behaviour
        app.open_node(fid)
        settle(app)
        check("Open shows the function's blocks", not app.behaviour_active() and app.project_blocks is handler["blocks"])
        app.open_node(node["id"])
        settle(app)
        check("reopening the window starts in the designer", not app.behaviour_active())
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
