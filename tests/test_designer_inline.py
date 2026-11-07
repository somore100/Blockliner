"""
Scripted UI test (run under Xvfb): typing straight onto the designer paper,
the Open button next to an event, and the widget blocks' dropdown.
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
    for _ in range(4):
        app.update_idletasks()
        app.update()


def text_of(ed, wid):
    return ed._dz_tree_now().find(wid)["props"].get("text")


def open_buttons(ed):
    found = []

    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == "Button" and c.cget("text") == "Open":
                found.append(c)
            walk(c)
    walk(ed._dz_root)
    return found


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

        # a freshly added label is ready to be typed into
        ed._dz_add_type("label")
        settle(app)
        wid = ed.state["sel"]
        check("adding a label opens the text box", ed._dz_inline is not None and ed._dz_inline["id"] == wid)
        ed._dz_inline["entry"].delete(0, "end")
        ed._dz_inline["entry"].insert(0, "Hello there")
        ed._dz_inline["entry"].event_generate("<Return>")
        settle(app)
        check("Enter keeps the typed text", text_of(ed, wid) == "Hello there")
        check("the text box is gone afterwards", ed._dz_inline is None)

        # Esc drops what was typed
        check("editing again works", ed._dz_edit_text(wid))
        ed._dz_inline["entry"].delete(0, "end")
        ed._dz_inline["entry"].insert(0, "never kept")
        ed._dz_inline["entry"].focus_force()            # key events go to the focused widget; Xvfb has no window manager to hand it over
        app.update()
        ed._dz_inline["entry"].event_generate("<Escape>")
        settle(app)
        check("Esc drops the typed text", text_of(ed, wid) == "Hello there" and ed._dz_inline is None)

        # clicking elsewhere on the paper keeps it
        ed._dz_edit_text(wid)
        ed._dz_inline["entry"].delete(0, "end")
        ed._dz_inline["entry"].insert(0, "Clicked away")
        box = ed._dz_box(wid)
        ox, oy = ed._dz_origin
        s = ed._dz_scale
        ed._dz_paper_press(SimpleNamespace(x=ox + (box["x"] + box["w"] + 60) * s, y=oy + (box["y"] + box["h"] + 60) * s,
                                           num=1, delta=0))
        settle(app)
        check("clicking away keeps the text", text_of(ed, wid) == "Clicked away")

        # the text box follows the camera
        ed._dz_edit_text(wid)
        before = app.designer_editor._dz_canvas.coords(app.designer_editor._dz_canvas.find_withtag("inline")[0])
        ed._dz_zoom_step(-1, 1.25, centre=True)
        settle(app)
        after = ed._dz_canvas.coords(ed._dz_canvas.find_withtag("inline")[0])
        check("the text box moves with the zoom", before != after)
        ed._dz_close_inline(commit=False)

        # widgets without text do nothing
        ed._dz_add_type("entry")
        settle(app)
        eid = ed.state["sel"]
        check("an input box has no text to type", ed._dz_inline is None and not ed._dz_edit_text(eid))

        # the window's title: only from its title strip
        root_id = ed._dz_tree_now().root["id"]
        check("the window title can be typed", ed._dz_edit_text(root_id))
        ed._dz_close_inline(commit=False)

        # event -> Open
        ed._dz_add_type("button")
        settle(app)
        bid = ed.state["sel"]
        check("a button's event row has no Open button yet", len(open_buttons(ed)) == 0)
        ed._dz_close_inline(commit=False)
        pick = ed._dz_tree_now().find(bid)
        new_id = ed._dz_new_handler(pick["name"], "command")
        ed._dz_apply(lambda t: t.set_event(bid, "command", new_id))
        settle(app)
        opened = []
        ed.port.open_node = lambda i: opened.append(i)
        labels = open_buttons(ed)
        check("an Open button shows once the event has a function", len(labels) == 1)
        if labels:
            labels[0].invoke()
            settle(app)
            check("Open shows that function", opened == [new_id])

        # widget blocks: the dropdown lists this window's widgets
        names = app.ui_widget_names()
        check("the widget dropdown lists the window's widgets", "root" in names and pick["name"] in names)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
