"""Scripted UI test (run under Xvfb): Node Output / Node Input blocks give a node real ports and a data wire,
and the generated code runs."""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import node_ports
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


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        settle(app)
        check("the palette has a Nodes category with both blocks", {"node_output", "node_input"} <= {
            b.get("block_id") for b in app.blocks_by_category.get("Nodes", [])})
        tab = app.tabs[app.active_tab_index]
        a = app.get_active_node(tab)
        a["name"] = "maker"
        a["blocks"][:] = [("assign_variable", {"variable": "raw", "value": "'abc'"}),
                          ("node_output", {"name": "text", "value": "raw.upper()"})]
        b = make_node("taker", node_id="tk", blocks=[("node_input", {"name": "text"}),
                                                     ("print_output", {"value": "text"})], order=next_order(tab["nodes"]))
        tab["nodes"].append(b)
        app.refresh_workspace()
        settle(app)
        check("the maker's output port is named after its Node Output", [p["name"] for p in node_ports.node_ports(a) if p["side"] == "out"] == ["text"])
        check("the taker's input port is named after its Node Input", [p["name"] for p in node_ports.node_ports(b) if p["side"] == "in"] == ["text"])
        uses = b.get("data_uses") or []
        check("the taker has a data wire from the maker", len(uses) == 1 and uses[0]["id"] == a["id"] and uses[0]["vars"] == ["text"])

        code = app.code_text.get("1.0", "end")
        check("the Node Output writes a normal assignment", "text = raw.upper()" in code)
        check("the Node Input writes only a comment", "# needs text from another node" in code)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(code, "<generated>", "exec"), {"__name__": "__generated__"})
        check("the generated code runs and passes the value on", out.getvalue().strip() == "ABC")

        app.goto_layer("nodes")
        settle(app)
        check("the Nodes layer draws the wire", len(app.workspace_canvas.find_withtag("wire")) > 0)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
