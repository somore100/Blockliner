"""
Files-layer scripted test (run under Xvfb): file-to-file import wire
resolution (recompute_file_references) and default tab canvas grid
placement (assign_default_tab_canvas_positions).

Not a pytest file - run directly, same convention as test_c2_canvas.py
etc. This only covers the backend derivation logic decided so far;
the actual files-as-boxes canvas rendering/dragging is not built yet
(next step in the Files-layer build order).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI, make_node

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()

    # Tab 0 ("Untitled 1", unsaved) gets an import that doesn't match
    # anything yet.
    tab0 = app.tabs[0]
    tab0["nodes"][0]["blocks"].append(("import_module", {"module": "helpers"}))
    app.recompute_file_references()
    check("unresolved import produces no file_references",
          tab0.get("file_references") == [])

    # Add a second tab and rename it (simulating either a saved file's
    # stem or a manually-renamed unsaved tab - resolution treats both
    # identically since title already mirrors the saved stem).
    app.new_tab()
    tab1 = app.tabs[1]
    tab1["title"] = "Helpers"  # different case on purpose
    app.recompute_file_references()

    check("import resolves case-insensitively once the target tab exists",
          app.tabs[0]["file_references"] == [1])
    check("target tab itself has no outgoing references",
          app.tabs[1].get("file_references") == [])

    # Self-import: tab importing its own title must never resolve.
    tab1["nodes"][0]["blocks"].append(("import_module", {"module": "Helpers"}))
    app.recompute_file_references()
    check("self-import never resolves", app.tabs[1]["file_references"] == [])

    # Import nested inside a category node must still be found (same
    # recursion all_function_nodes()/iter_all_blocks_recursive() already
    # provide for func_call in Phase C1).
    app.new_tab()
    tab2 = app.tabs[2]
    category = make_node("Utils", node_id="cat1", kind="category", blocks=[])
    inner_fn = make_node("inner", node_id="inner1", blocks=[
        ("import_module", {"module": "helpers"}),
    ])
    category["child_nodes"] = [inner_fn]
    tab2["nodes"].append(category)
    app.recompute_file_references()
    check("import nested inside a category still resolves",
          app.tabs[2]["file_references"] == [1])

    # --- Default tab canvas positions ---
    for t in app.tabs:
        t.pop("canvas_x", None)
        t.pop("canvas_y", None)
    app.tabs[0]["canvas_x"] = 999
    app.tabs[0]["canvas_y"] = 999
    app.assign_default_tab_canvas_positions()
    check("existing tab position is never overwritten",
          app.tabs[0]["canvas_x"] == 999 and app.tabs[0]["canvas_y"] == 999)
    check("tabs without a position get one assigned",
          all("canvas_x" in t and "canvas_y" in t for t in app.tabs))
    check("grid positions differ across tabs",
          len({(t["canvas_x"], t["canvas_y"]) for t in app.tabs}) == len(app.tabs))

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll Files-layer reference/canvas-default assertions passed.")


if __name__ == "__main__":
    main()
