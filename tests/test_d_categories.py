"""
Phase D scripted UI test (run under Xvfb): category nodes (pure visual
folders, zero codegen effect).

Not a pytest file - run directly, same convention as
test_c2_canvas.py/test_c3_wiredrag.py. Builds nodes directly via
make_node() + list mutation (same convention test_c2_canvas.py uses)
rather than calling create_node()/create_category(), since those pop a
real blocking simpledialog.askstring() prompt that never returns
headless - the dialogs are thin argument-gathering wrappers, the
actual logic under test lives in open_node()/get_current_node_list()/
all_tab_blocks_concatenated(), which this drives directly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from ui import BlocklinerUI, make_node, find_node_by_id

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()

    tab = app.tabs[app.active_tab_index]
    node_a = tab["nodes"][0]
    node_a["name"] = "main"
    node_a["blocks"].append(("print", {"value": "'hello'"}))

    app.switch_to_file_view()
    app.update()

    # --- Add a category at top level (same shape create_category()
    # builds), confirm open_node() navigates into it like a class ---
    category = make_node("Utils", node_id="cat1", kind="category", child_nodes=[])
    tab["nodes"].append(category)
    app.mark_active_tab_dirty()
    app.open_node(category["id"])
    app.update()
    check("category is category-kind", category.get("kind") == "category")
    check("open_node navigated inside the category (file_view_path updated)",
          tab.get("file_view_path") == [category["id"]])

    # --- Add a function node inside the category (mirrors what
    # create_node() would append to get_current_node_list()'s result) ---
    inner = make_node("helper", node_id="inner1", blocks=[])
    app.get_current_node_list(tab).append(inner)
    app.mark_active_tab_dirty()
    app.open_node(inner["id"])
    app.update()
    check("node created inside category ends up in category's child_nodes",
          any(n["id"] == inner["id"] for n in category["child_nodes"]))
    inner["blocks"].append(("print", {"value": "'from inside category'"}))

    # --- Category must have zero codegen effect: no wrapping, blocks
    # from inside it still concatenate into generated code exactly
    # like a top-level node's would ---
    app.switch_to_file_view()
    app.update()
    all_blocks = app.all_tab_blocks_concatenated()
    check("category's own blocks list stays empty (container, not a block holder)",
          category["blocks"] == [])
    check("blocks nested inside the category are still concatenated for codegen",
          any(b[0] == "print" and b[1].get("value") == "'from inside category'"
              for b in all_blocks))
    check("category introduces no wrapping class name",
          app.get_wrapping_class_name(tab, "python") != category["name"])

    # --- File view rendering: category box exists at top level; the
    # function node inside it only appears once navigated in; the
    # category box itself never gets a wire-drag port ---
    check("category box rendered in file view", category["id"] in app._fileview_boxes)
    _, category_box = app._fileview_boxes[category["id"]]
    header = category_box.winfo_children()[0]
    has_port = any(w.cget("cursor") == "crosshair" for w in header.winfo_children())
    check("category box has no wire-drag port", not has_port)

    app.open_node(category["id"])
    app.update()
    check("navigated into category shows the inner function node",
          inner["id"] in app._fileview_boxes)

    # --- Nested categories: a category inside a category still works
    # via the same generic child_nodes/file_view_path machinery ---
    nested_category = make_node("Nested", node_id="cat2", kind="category", child_nodes=[])
    app.get_current_node_list(tab).append(nested_category)
    app.mark_active_tab_dirty()
    app.open_node(nested_category["id"])
    app.update()
    check("nested category created inside the first category",
          any(n["id"] == nested_category["id"] for n in category["child_nodes"]))
    check("find_node_by_id finds a node nested two categories deep",
          find_node_by_id(tab["nodes"], nested_category["id"]) is not None)

    # --- Regression: switching back to node view and back still works ---
    app.switch_to_file_view()
    app.update()
    app.open_node(inner["id"])
    app.update()
    check("opening the inner function node still opens the block editor",
          app.view_mode == "node" and tab["active_node_id"] == inner["id"])

    # Screenshot for a visual sanity check
    app.switch_to_file_view()
    app.update()
    try:
        import subprocess
        subprocess.run(["import", "-window", "root", "/tmp/d_categories.png"],
                        check=False, timeout=10)
    except Exception as e:
        print("screenshot skipped:", e)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("All Phase D category assertions passed.")


if __name__ == "__main__":
    main()
