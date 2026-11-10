"""Scripted UI test (run under Xvfb): right-click > Make this node a function turns the node into a
Define Function, nodes that used its output call it, the program prints the same, and Undo brings it back."""
import contextlib
import io
import os
import sys
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import node_ports
from nodes_model import find_node_by_id, make_node
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(6):
        app.update_idletasks()
        app.update()


def run(app):
    code = app.code_text.get("1.0", "end")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<generated>", "exec"), {"__name__": "__generated__"})
    return out.getvalue().split(), code


def main():
    answers = []
    messagebox.askyesno = lambda *a, **k: (answers.append(a), True)[1]
    messagebox.showinfo = lambda *a, **k: answers.append(a)
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]
        start = app.get_active_node(tab)
        start["name"], start["order"] = "start", 0
        start["blocks"][:] = [("assign_variable", {"variable": "base", "value": "'a'"})]
        maker = make_node("maker", node_id="mk", order=1, blocks=[
            ("node_input", {"name": "base"}), ("assign_variable", {"variable": "raw", "value": "base + 'bc'"}),
            ("node_output", {"name": "text", "value": "raw.upper()"})])
        taker = make_node("taker", node_id="tk", order=2, blocks=[("print_output", {"value": "text"})])
        tab["nodes"].extend([maker, taker])
        app.refresh_workspace()
        settle(app)
        before, _ = run(app)
        check("before: the program prints ABC", before == ["ABC"])

        menu = app.build_node_menu("mk")
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        check("the node's right-click menu offers it", any(l.startswith("Make this node a function") for l in labels))

        app.make_node_function_dialog("mk")
        settle(app)
        check("the user was asked first", len(answers) == 1)
        maker = find_node_by_id(tab["nodes"], "mk")
        check("the node is a function now", node_ports.has_function(maker))
        after, code = run(app)
        check("the program still prints ABC", after == ["ABC"])
        check("the function comes first in the code", code.index("def maker(base):") < code.index("print(text)"))
        check("the caller assigns the result", "text = maker(base)" in code)
        check("the box ports keep their names", node_ports.node_interface(maker) == (["base"], ["text"]))
        check("a change bar tells what happened", getattr(app, "_change_bar", None) is not None)

        menu = app.build_node_menu("mk")
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        check("it is no longer offered for a function node", not any(l.startswith("Make this node a function") for l in labels))

        check("Undo brings the old blocks back", app.undo_project())
        settle(app)
        maker = find_node_by_id(app.tabs[app.active_tab_index]["nodes"], "mk")      # undo swaps in fresh node objects
        check("after undo it is an ordinary node again", not node_ports.has_function(maker)
              and [b[0] for b in maker["blocks"]] == ["node_input", "assign_variable", "node_output"])
        check("and the program still prints ABC", run(app)[0] == ["ABC"])
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
