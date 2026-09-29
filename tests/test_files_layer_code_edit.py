"""
Scripted UI test (run under Xvfb): the Files-layer 'View Code' toggle is
now editable PER NODE (all nodes of all open tabs, including ones nested
in category/class nodes). Covers the parts that are easy to get wrong:

  * tabs in a DIFFERENT language than the active one render and commit
    against their own pack, and the loaded pack is restored afterwards
  * editing one node never touches its siblings or other tabs
  * an edit to the ACTIVE node survives sync_active_tab_state() (a
    stale project_blocks pointer used to be able to revert it - this
    also guards the Nodes-layer editor, which shared the bug)
  * stale/guarded commits are safe no-ops
  * an edited `import` line redraws the Files-layer wires

Not a pytest file - run directly, same convention as the other tests.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from ui import BlocklinerUI, make_node, default_active_node_id

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def text_widgets(app):
    return [w for w in app.workspace_frame.winfo_children() if isinstance(w, tk.Text)]


def set_text(widget, text):
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()

    # --- Tab 0: python. Two sibling nodes + a category holding a child. ---
    tab0 = app.tabs[0]
    tab0["title"] = "main"
    node_a = make_node("NodeA", node_id=901,
                       blocks=[("assign_variable", {"variable": "x", "value": "1"})])
    node_b = make_node("NodeB", node_id=902,
                       blocks=[("assign_variable", {"variable": "y", "value": "2"})])
    child = make_node("Child", node_id=904,
                      blocks=[("assign_variable", {"variable": "c", "value": "3"})])
    category = make_node("Folder", node_id=903, kind="category", child_nodes=[child])
    tab0["nodes"] = [node_a, node_b, category]
    tab0["active_node_id"] = node_a["id"]
    app.project_blocks = node_a["blocks"]

    # --- Tab 1: javascript (a different language than the active tab). ---
    js_nodes = app.build_initial_nodes_for_language("javascript")
    js_node = js_nodes[0]
    js_node["blocks"] = [("assign_variable", {"variable": "a", "value": "1"})]
    app.tabs.append({
        "title": "helper", "language": "javascript", "nodes": js_nodes,
        "active_node_id": default_active_node_id(js_nodes),
        "filepath": None, "dirty": False,
    })

    app.switch_to_files_view()
    app.toggle_files_view_code_mode()
    app.update()

    check("Files layer code view is on", app.view_mode == "files" and app.files_view_code_mode)
    widgets = text_widgets(app)
    check("one editable box per function node across all tabs "
          "(NodeA, NodeB, Child, JS main node)", len(widgets) == 4)
    check("all boxes are editable", all(str(w.cget("state")) == "normal" for w in widgets))
    check("NodeA box shows only NodeA's code",
          "x = 1" in widgets[0].get("1.0", tk.END) and "y = 2" not in widgets[0].get("1.0", tk.END))
    check("nested Child box shows its own code", "c = 3" in widgets[2].get("1.0", tk.END))
    check("JS tab renders with the JS pack (let a = 1;), not the Python one",
          "let a = 1;" in widgets[3].get("1.0", tk.END))

    labels = [str(w.cget("text")) for w in app.workspace_frame.winfo_children()
              if isinstance(w, tk.Label)]
    check("nested node is labelled with its parent path",
          any("Folder" in t and "Child" in t for t in labels))

    python_blocks_obj = app.blocks
    check("active language pack is Python before any cross-language edit",
          app.current_language == "python")

    # --- Edit the INACTIVE JS tab's node: must match against the JS pack. ---
    set_text(widgets[3], "if (x) {\n    let y = 1;\n}\n")
    app._on_files_node_code_focus_out(app.tabs[1], js_node, widgets[3])
    app.update()
    check("JS edit produced a real if_statement container with a child",
          js_node["blocks"] and js_node["blocks"][0][0] == "if_statement"
          and len(js_node["blocks"][0][1]["_children"]) == 1)
    check("JS tab is marked dirty, Python tab is not", app.tabs[1]["dirty"] and not tab0["dirty"])
    check("loaded pack + language restored after the cross-language edit",
          app.current_language == "python" and app.blocks is python_blocks_obj)
    check("Python tab's nodes untouched by the JS edit",
          node_a["blocks"] == [("assign_variable", {"variable": "x", "value": "1"})]
          and node_b["blocks"] == [("assign_variable", {"variable": "y", "value": "2"})])

    # --- Edit a nested node in the active tab; siblings stay put. ---
    widgets = text_widgets(app)
    set_text(widgets[2], "c = 3\nd = 4\n")
    app._on_files_node_code_focus_out(tab0, child, widgets[2])
    app.update()
    check("nested Child now has 2 blocks", len(child["blocks"]) == 2)
    check("siblings NodeA/NodeB unchanged by editing Child",
          len(node_a["blocks"]) == 1 and len(node_b["blocks"]) == 1)

    # --- Regression: editing the ACTIVE node must survive a sync. ---
    widgets = text_widgets(app)
    set_text(widgets[0], "x = 1\nz = 9\n")
    app._on_files_node_code_focus_out(tab0, node_a, widgets[0])
    app.update()
    check("active node edited via Files layer (2 blocks)", len(node_a["blocks"]) == 2)
    check("project_blocks re-pointed to the edited list", app.project_blocks is node_a["blocks"])
    app.sync_active_tab_state()
    check("edit survives sync_active_tab_state() (no stale-pointer revert)",
          len(node_a["blocks"]) == 2 and app.get_active_node(tab0)["blocks"] is node_a["blocks"])

    # Same guarantee for the Nodes-layer editor (it shared the bug).
    app.switch_to_file_view()
    app.toggle_file_view_code_mode()
    app.update()
    nw = text_widgets(app)
    set_text(nw[0], "x = 1\nz = 9\nq = 7\n")
    app._on_node_code_focus_out(node_a, nw[0])
    app.update()
    app.sync_active_tab_state()
    check("Nodes-layer edit of the active node also survives a sync",
          len(node_a["blocks"]) == 3 and app.project_blocks is node_a["blocks"])

    # --- Guards: stale commits are safe no-ops. ---
    app.switch_to_files_view()
    app.toggle_files_view_code_mode()
    app.update()
    widgets = text_widgets(app)
    before = list(node_b["blocks"])
    set_text(widgets[1], "totally = 'different'\n")
    app.files_view_code_mode = False  # layer no longer showing code
    app._on_files_node_code_focus_out(tab0, node_b, widgets[1])
    check("commit while the code view is off is a no-op", node_b["blocks"] == before)
    app.files_view_code_mode = True

    ghost_tab = {"title": "ghost", "language": "python", "nodes": [make_node("G", node_id=990)],
                 "active_node_id": 990, "filepath": None, "dirty": False}
    stray = tk.Text(app.workspace_frame)
    stray.insert("1.0", "q = 1\n")
    app._on_files_node_code_focus_out(ghost_tab, ghost_tab["nodes"][0], stray)
    check("commit for a tab that isn't open is a no-op", ghost_tab["nodes"][0]["blocks"] == [])

    gone = make_node("Gone", node_id=991)
    app._on_files_node_code_focus_out(tab0, gone, stray)
    check("commit for a node no longer in the tab is a no-op", gone["blocks"] == [])

    # --- An edited import line redraws the Files-layer wires. ---
    app.tabs[1]["title"] = "helper"
    widgets = text_widgets(app)
    set_text(widgets[1], "import helper\n")
    app._on_files_node_code_focus_out(tab0, node_b, widgets[1])
    app.update()
    check("typing 'import helper' created a file reference to the 'helper' tab",
          any(node_b["blocks"][i][0] == "import_module" for i in range(len(node_b["blocks"])))
          and len(tab0.get("file_references", [])) == 1)

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll Files-layer code-edit assertions passed.")


if __name__ == "__main__":
    main()
