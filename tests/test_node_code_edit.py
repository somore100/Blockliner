"""
Scripted UI test (run under Xvfb): build-order item 3, option 1 - the
Nodes-layer 'View Code' toggle is now editable PER NODE rather than a
single read-only whole-tab blob. Covers the actual point of the
design-fork decision: editing one node's code never touches a sibling
node's blocks, and class/category nodes (which hold other nodes, not
blocks) never get an editable widget at all.

Not a pytest file - run directly, same convention as
test_nodes_layer_code_toggle.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from ui import BlocklinerUI, make_node

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def text_widgets_in(frame):
    return [w for w in frame.winfo_children() if isinstance(w, tk.Text)]


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()
    tab = app.tabs[0]

    # --- Set up two sibling function nodes plus a category, so editing
    # one node's code is meaningfully distinguishable from touching
    # everything else in the tab. ---
    node_a = make_node("NodeA", node_id=901,
                        blocks=[("assign_variable", {"variable": "x", "value": "1"})])
    node_b = make_node("NodeB", node_id=902,
                        blocks=[("assign_variable", {"variable": "y", "value": "2"})])
    category = make_node("Folder", node_id=903, kind="category", child_nodes=[])
    tab["nodes"] = [node_a, node_b, category]
    tab["active_node_id"] = node_a["id"]

    app.switch_to_file_view()
    app.file_view_code_mode = False
    app.toggle_file_view_code_mode()
    app.update()

    check("view_mode is 'file' (Nodes layer)", app.view_mode == "file")
    check("file_view_code_mode is on", app.file_view_code_mode is True)

    widgets = text_widgets_in(app.workspace_frame)
    check("exactly two editable Text widgets (category gets none)", len(widgets) == 2)
    check("both node widgets are editable", all(str(w.cget("state")) == "normal" for w in widgets))
    check("NodeA's widget shows its own code, not NodeB's", "x = 1" in widgets[0].get(1.0, tk.END)
          and "y = 2" not in widgets[0].get(1.0, tk.END))
    check("NodeB's widget shows its own code, not NodeA's", "y = 2" in widgets[1].get(1.0, tk.END)
          and "x = 1" not in widgets[1].get(1.0, tk.END))

    labels = [w for w in app.workspace_frame.winfo_children() if isinstance(w, tk.Label)]
    check("category node gets a non-editable note instead of a Text widget",
          any("open it" in str(w.cget("text")).lower() for w in labels))

    # --- Editing NodeA's text and committing (FocusOut) must only
    # change NodeA's blocks - NodeB and the category must be untouched. ---
    app._on_node_code_focus_out(node_a, widgets[0])  # no-op: unchanged text
    check("no-op commit leaves NodeA's blocks alone",
          node_a["blocks"] == [("assign_variable", {"variable": "x", "value": "1"})])

    widgets[0].delete("1.0", tk.END)
    widgets[0].insert("1.0", "x = 1\nz = 9\n")
    app._on_node_code_focus_out(node_a, widgets[0])
    app.update()

    check("NodeA's blocks now reflect the edited text (2 lines)", len(node_a["blocks"]) == 2)
    check("NodeB's blocks are untouched by editing NodeA",
          node_b["blocks"] == [("assign_variable", {"variable": "y", "value": "2"})])
    check("category node still has no blocks after a sibling edit", category["blocks"] == [])

    # --- Widgets are rebuilt after commit (refresh_workspace) - the
    # new one for NodeA should show the freshly matched code. ---
    rebuilt = text_widgets_in(app.workspace_frame)
    check("still two editable widgets after the commit rebuild", len(rebuilt) == 2)
    check("rebuilt NodeA widget shows the newly matched code",
          "z = 9" in rebuilt[0].get(1.0, tk.END))

    # --- Clearing a node's code entirely must empty its blocks, not
    # leave a stray raw_code block behind for blank text. ---
    rebuilt[1].delete("1.0", tk.END)
    app._on_node_code_focus_out(node_b, rebuilt[1])
    app.update()
    check("clearing NodeB's text empties its blocks", node_b["blocks"] == [])

    # --- Adversarial: indentation-sensitive round trips ---
    def commit_text(node, text):
        w = text_widgets_in(app.workspace_frame)[tab["nodes"].index(node)]
        w.delete("1.0", tk.END)
        w.insert("1.0", text)
        app._on_node_code_focus_out(node, w)
        app.update()

    nested = "x = 5\nif x > 3:\n    print(x)\n    y = 2\nprint('done')\n"
    commit_text(node_a, nested)
    check("nested code round-trips byte-identically",
          app.generate_code_for_node(node_a, "python") == nested)
    leaked = [
        v for bid, p in node_a["blocks"] if bid != "raw_code" for v in p.values()
        if isinstance(v, str) and v[:1] in (" ", "\t")
    ]
    check("no param value has leading whitespace baked in", leaked == [])
    if_blocks = [b for b in node_a["blocks"] if b[0] == "if_statement"]
    check("nested if became a real if_statement container", len(if_blocks) == 1)
    check("if body lines became real child blocks (2 children, condition 'x > 3')",
          len(if_blocks) == 1 and if_blocks[0][1]["condition"] == "x > 3"
          and len(if_blocks[0][1]["_children"]) == 2)

    deep = "def f(a):\n    for i in range(3):\n        print(i)\n    return a\nf(1)\n"
    commit_text(node_a, deep)
    check("def > for > print nesting round-trips byte-identically",
          app.generate_code_for_node(node_a, "python") == deep)
    fd = node_a["blocks"][0]
    check("func_def holds a loop_for child which holds a print child",
          fd[0] == "func_def" and fd[1]["_children"][0][0] == "loop_for"
          and fd[1]["_children"][0][1]["_children"][0][0] == "print_output")

    commit_text(node_a, "while x < 3:\n    x = x + 1\n")
    check("while with a comparison condition becomes a loop_while container",
          node_a["blocks"][0][0] == "loop_while")

    commit_text(node_a, "if x:\n    pass\n")
    check("a body that is just 'pass' becomes an empty container",
          node_a["blocks"][0][0] == "if_statement" and node_a["blocks"][0][1]["_children"] == [])

    commit_text(node_a, "if x:\n")
    check("header with no body yet (mid-typing) stays raw, no crash, no hang",
          node_a["blocks"] == [("raw_code", {"code": "if x:"})])

    els = "if x:\n    y = 1\nelse:\n    y = 2\n"
    commit_text(node_a, els)
    check("if/else round-trips byte-identically",
          app.generate_code_for_node(node_a, "python") == els)
    check("else became a real else_statement container with its own child",
          [b[0] for b in node_a["blocks"]] == ["if_statement", "else_statement"]
          and len(node_a["blocks"][1][1]["_children"]) == 1)

    chain = ("if x == 1:\n    a = 1\nelif x == 2:\n    a = 2\nelif x == 3:\n"
             "    a = 3\nelse:\n    a = 0\nprint(a)\n")
    commit_text(node_a, chain)
    check("if/elif/elif/else chain round-trips byte-identically",
          app.generate_code_for_node(node_a, "python") == chain)
    check("chain is 3 containers + else + trailing print, all real blocks, no raw",
          [b[0] for b in node_a["blocks"]] ==
          ["if_statement", "elif_statement", "elif_statement", "else_statement", "print_output"])
    check("elif conditions captured", node_a["blocks"][1][1]["condition"] == "x == 2"
          and node_a["blocks"][2][1]["condition"] == "x == 3")

    nested_else = "for i in range(3):\n    if i:\n        a = 1\n    else:\n        a = 2\n"
    commit_text(node_a, nested_else)
    check("else nested inside a for/if round-trips and is a real block",
          app.generate_code_for_node(node_a, "python") == nested_else
          and node_a["blocks"][0][1]["_children"][1][0] == "else_statement")

    commit_text(node_a, "else:\n")
    check("bare 'else:' with no body yet stays raw, no hang", node_a["blocks"][0][0] == "raw_code")

    commit_text(node_a, "x = 1\nelse:\n    y = 2\n")
    check("stray else with no preceding if is still kept losslessly",
          app.generate_code_for_node(node_a, "python") == "x = 1\nelse:\n    y = 2\n")

    weird = "while_typo x:\nfoo bar baz\n"
    commit_text(node_a, weird)
    check("unrecognized lines fall back to raw code, nothing lost",
          app.generate_code_for_node(node_a, "python") == weird
          and len(node_a["blocks"]) == 2)

    commit_text(node_a, "\tx = 5\n\n\n   y = 6   \n")
    check("leading tabs become 4 spaces, trailing spaces stripped, odd indent untouched",
          app.generate_code_for_node(node_a, "python") == "    x = 5\n   y = 6\n")

    from engine.formatter import normalize_line, normalize_text
    check("normalize_line: tabs + trailing ws", normalize_line("\t\tx = 1  \t") == "        x = 1")
    check("normalize_line: interior tabs/spaces untouched", normalize_line("a\tb  c") == "a\tb  c")
    check("normalize_line: blank/whitespace-only line -> empty", normalize_line("  \t ") == "")
    check("normalize_text is idempotent",
          normalize_text(normalize_text("\tif x:\n\t\ty  \n")) == normalize_text("\tif x:\n\t\ty  \n"))

    # Editing after the node was deleted elsewhere must not raise.
    ghost = make_node("Ghost", node_id=999)
    stray = tk.Text(app.workspace_frame)
    stray.insert("1.0", "q = 1\n")
    app._on_node_code_focus_out(ghost, stray)
    check("commit against a node no longer in the tab is a safe no-op",
          ghost["blocks"] == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll per-node code-edit assertions passed.")


if __name__ == "__main__":
    main()
