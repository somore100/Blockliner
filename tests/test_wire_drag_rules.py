"""Scripted UI test (run under Xvfb): a wire dragged to a plain node sets run order instead of writing a
call to a non-function, a wire to a function node writes a real call, and the generated code runs."""
import contextlib
import io
import os
import sys
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes_model import make_node, next_order
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


def run_code(app):
    """Run the generated code in this process; (0 if it ran, what it printed, the error)."""
    code = app.code_text.get("1.0", "end")
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(code, "<generated>", "exec"), {"__name__": "__generated__"})
        return 0, out.getvalue(), ""
    except Exception as e:                              # NameError is what a bad wire used to cause
        return 1, out.getvalue(), repr(e)


def main():
    shown = []
    messagebox.showinfo = lambda *a, **k: shown.append(a)
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]
        main_node = app.get_active_node(tab)
        main_node["blocks"][:] = [("print_output", {"value": "'hello from main'"})]
        plain = make_node("greeter", node_id="gg", blocks=[("print_output", {"value": "'hi from greeter'"})], order=next_order(tab["nodes"]))
        third = make_node("last", node_id="ll", blocks=[("print_output", {"value": "'last'"})], order=next_order(tab["nodes"]) + 1)
        tab["nodes"].extend([plain, third])
        third["order"] = 3

        app.add_wire_by_drag(main_node["id"], "gg")
        settle(app)
        check("a wire to a plain node writes no call", not any(b[0] == "func_call" for b in main_node["blocks"]))
        check("it sets the run order right after the source", plain["order"] == main_node["order"] + 1)
        check("the code still runs", run_code(app)[0] == 0)
        
        # a function node: called, and written before its caller whatever the numbers say
        fn = make_node("shout", node_id="ff", blocks=[("func_def", {"name": "shout", "params": "text",
                                                                    "_children": [("print_output", {"value": "text"})]})],
                       order=9)
        tab["nodes"].append(fn)
        app.add_wire_by_drag(main_node["id"], "ff")
        settle(app)
        call = main_node["blocks"][-1]
        check("a wire to a function node writes a real call", call[0] == "func_call" and call[1]["name"] == "shout")
        call[1]["args"] = "'wired'"
        app.refresh_workspace()
        settle(app)
        rc, out, err = run_code(app)
        check("the function is defined before its caller although its number is higher", rc == 0 and "wired" in out)
        check("the function's code comes first in the file", app.code_text.get("1.0", "end").index("def shout")
              < app.code_text.get("1.0", "end").index("hello from main"))

        # a wire to nothing useful
        before = len(shown)
        main_node["order"] = None
        app.add_wire_by_drag(main_node["id"], "ll")
        check("an anchor that is not set to run says so", len(shown) == before + 1)
        app.add_wire_by_drag(main_node["id"], main_node["id"])
        check("a node can't be wired to itself", len(shown) == before + 1)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
