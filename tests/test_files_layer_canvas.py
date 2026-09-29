"""
Files-layer scripted UI test (run under Xvfb): the files-as-boxes
canvas itself (render_files_view/create_filesview_file_box/
draw_file_wires) and layer navigation (switch_to_files_view/
open_file_from_files_view). Companion to test_files_layer_refs.py,
which covers the backend derivation this renders.

Not a pytest file - run directly, same convention as test_c2_canvas.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.update()

    # Second tab, wired to the first via import_module, mirroring
    # test_files_layer_refs.py's setup.
    app.new_tab()
    app.tabs[1]["title"] = "helpers"
    app.tabs[0]["nodes"][0]["blocks"].append(("import_module", {"module": "helpers"}))

    app.switch_to_files_view()
    app.update()

    # --- Structural checks ---
    check("view_mode is files", app.view_mode == "files")
    check("both tabs got file boxes", set(app._filesview_boxes.keys()) == {0, 1})
    check("tabs got default grid positions",
          all("canvas_x" in t and "canvas_y" in t for t in app.tabs))

    wire_items = app.workspace_canvas.find_withtag("wire")
    check("an import wire was drawn", len(wire_items) > 0)

    # --- Drag a file box and confirm its position + wire redraw ---
    tab0_before = (app.tabs[0]["canvas_x"], app.tabs[0]["canvas_y"])
    _, box0 = app._filesview_boxes[0]
    header0 = box0.winfo_children()[0]
    header0.event_generate("<ButtonPress-1>", x=5, y=5)
    header0.event_generate("<B1-Motion>", x=55, y=45)
    header0.event_generate("<ButtonRelease-1>", x=55, y=45)
    app.update()
    tab0_after = (app.tabs[0]["canvas_x"], app.tabs[0]["canvas_y"])
    check("dragging a file box actually changed its position", tab0_before != tab0_after)
    check("wire still drawn after drag", len(app.workspace_canvas.find_withtag("wire")) > 0)

    # --- Navigation: open a file from the Files layer ---
    app.open_file_from_files_view(1)
    app.update()
    check("opening a file from Files layer lands on Nodes layer (view_mode=='file')",
          app.view_mode == "file")
    check("opening a file from Files layer switches the active tab",
          app.active_tab_index == 1)

    # Nodes-layer top level should now offer a "Files" back button
    # (this tab has one node, so no "Nodes" button existed before -
    # unrelated to the new "Files" one being present).
    back_texts = [
        w["text"] for w in app.node_nav_frame.winfo_children()
        if isinstance(w, tk.Button)
    ]
    check("'<- Files' back button present at the top of the Nodes layer",
          any("Files" in t for t in back_texts))

    # --- Round-trip back to Files layer ---
    app.switch_to_files_view()
    app.update()
    check("switch_to_files_view returns to view_mode=='files'", app.view_mode == "files")
    check("Files layer canvas still shows both boxes after round-trip",
          set(app._filesview_boxes.keys()) == {0, 1})

    # --- Clean canvas handoff back to node/block editor ---
    app.open_file_from_files_view(1)
    app.update()
    check("no stray file boxes left after leaving Files layer",
          len(app.workspace_canvas.find_withtag("file_box")) == 0)

    # --- "View Code" toggle ---
    app.switch_to_files_view()
    app.update()
    check("files_view_code_mode starts False on entering Files layer",
          app.files_view_code_mode is False)

    app.toggle_files_view_code_mode()
    app.update()
    check("toggle flips files_view_code_mode on", app.files_view_code_mode is True)

    text_widgets = [w for w in app.workspace_frame.winfo_children() if isinstance(w, tk.Text)]
    check("one Text widget rendered per open tab", len(text_widgets) == len(app.tabs))
    check("no file boxes drawn while in code view",
          len(app.workspace_canvas.find_withtag("file_box")) == 0)

    contents = [t.get("1.0", tk.END) for t in text_widgets]
    check("the importing file's code view contains its import line",
          any("import helpers" in c for c in contents))
    # The Files-layer code view is editable per node now (see
    # test_files_layer_code_edit.py for the editing/commit behavior).
    check("code view text widgets are editable, not read-only",
          all(str(t.cget("state")) == "normal" for t in text_widgets))

    app.toggle_files_view_code_mode()
    app.update()
    check("toggle flips files_view_code_mode back off", app.files_view_code_mode is False)
    check("file boxes are back after toggling off",
          set(app._filesview_boxes.keys()) == {0, 1})

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll Files-layer canvas assertions passed.")


if __name__ == "__main__":
    main()
