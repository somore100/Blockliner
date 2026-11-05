"""
Scripted UI test (run under Xvfb): choosing another language in the dropdown.
A file with a UI design refuses; a file with blocks asks first (Cancel keeps
everything); an empty file switches freely.
"""
import os
import sys
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


def main():
    asked, told = [], []
    answer = {"yes": False}
    messagebox.askyesno = lambda *a, **k: (asked.append(a), answer["yes"])[1]
    messagebox.showinfo = lambda *a, **k: told.append(a)
    messagebox.showerror = lambda *a, **k: None

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.ask_ui_pack = lambda packs: packs[0]            # several UI libraries: never block on the chooser
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]

        # empty file: no question
        app.lang_var.set("c")
        app.on_language_pick()
        settle(app)
        check("an empty file switches without asking", tab["language"] == "c" and not asked and not told)
        app.lang_var.set("python")
        app.on_language_pick()
        settle(app)

        # a file with blocks: Cancel keeps everything
        node = app.get_active_node(tab)
        node["blocks"].append(("print_output", {"value": "1"}))
        app.lang_var.set("c")
        answer["yes"] = False
        app.on_language_pick()
        settle(app)
        check("Cancel keeps the language", tab["language"] == "python" and app.lang_var.get() == "python")
        check("Cancel keeps the blocks", len(node["blocks"]) == 1 and len(asked) == 1)

        # Continue switches and empties
        answer["yes"] = True
        app.lang_var.set("c")
        app.on_language_pick()
        settle(app)
        check("Continue switches the language", tab["language"] == "c")
        check("Continue empties the blocks", all(not n["blocks"] for n, _p in app.iter_tab_nodes(tab)))

        # a file with a UI design refuses
        app.lang_var.set("python")
        app.on_language_pick()
        settle(app)
        ui = app.create_starter_node("ui", (80, 80))
        settle(app)
        check("a UI node exists", ui is not None and ui_node.is_ui_node(ui))
        told.clear()
        app.lang_var.set("csharp")
        app.on_language_pick()
        settle(app)
        check("a UI design blocks the switch", tab["language"] == "python" and app.lang_var.get() == "python" and len(told) == 1)
        check("the UI node is untouched", ui_node.is_ui_node(ui) and not ui_node.is_detached(ui))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
