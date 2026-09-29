"""
Scripted UI test (run under Xvfb): the Nodes-layer 'View Code' toggle,
the right-hand Generated Code panel becoming Blocks-layer-only, and
Export/Code->Blocks staying independent of panel/toggle visibility.

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

    # --- Right panel: Blocks layer (default view_mode == "node") ---
    check("right panel visible by default (Blocks layer)",
          bool(app.right_panel.winfo_manager()))

    # --- Nodes layer: panel hides, no toggle shown yet enters canvas ---
    app.switch_to_file_view()
    app.update()
    check("right panel hidden at Nodes layer (canvas sub-mode)",
          not app.right_panel.winfo_manager())
    check("file_view_code_mode starts False on entering Nodes layer",
          app.file_view_code_mode is False)

    # code_text should still be current even though the panel is hidden -
    # this is the whole point of calling update_generated_code()
    # unconditionally.
    app.tabs[0]["nodes"][0]["blocks"].append(("import_module", {"module": "os"}))
    app.refresh_workspace()
    hidden_code = app.code_text.get(1.0, tk.END)
    check("code_text stays current while the panel is hidden",
          "import os" in hidden_code)

    # --- Toggle to code view at the Nodes layer ---
    app.toggle_file_view_code_mode()
    app.update()
    check("view_mode still 'file' after toggling code view", app.view_mode == "file")
    check("right panel still hidden while Nodes-layer code view is on",
          not app.right_panel.winfo_manager())
    nodes_code_widgets = [
        w for w in app.workspace_frame.winfo_children() if isinstance(w, tk.Text)
    ]
    check("exactly one code Text widget shown at Nodes layer", len(nodes_code_widgets) == 1)
    check("Nodes-layer code view contains the tab's own code",
          "import os" in nodes_code_widgets[0].get(1.0, tk.END))
    # Build-order item 3 (option 1): the Nodes-layer code view is now
    # editable per-node, not a read-only whole-tab blob - see
    # test_node_code_edit.py for the editing/commit behavior itself.
    check("Nodes-layer per-node code view is editable, not read-only",
          str(nodes_code_widgets[0].cget("state")) == "normal")

    # Toggle back off - boxes should return.
    app.toggle_file_view_code_mode()
    app.update()
    check("no stray file-view boxes replaced by canvas boxes after toggling off",
          len(app._fileview_boxes) > 0)

    # --- Back to Blocks layer: panel returns unchanged ---
    active_node = app.get_active_node(app.tabs[0])
    app.open_node(active_node["id"]) if hasattr(app, "open_node") else None
    app.view_mode = "node"
    app.refresh_workspace()
    app.update()
    check("right panel visible again at Blocks layer", bool(app.right_panel.winfo_manager()))

    # --- Files layer: panel still hidden (own toggle handles code view) ---
    app.switch_to_files_view()
    app.update()
    check("right panel hidden at Files layer too", not app.right_panel.winfo_manager())

    # --- Code -> Blocks dialog: reachable and independent of panel/toggle ---
    dialog = app.open_code_to_blocks_dialog(prefill_from_file=False)
    app.update()
    check("Code->Blocks dialog opens while at the Files layer (panel hidden)",
          isinstance(dialog, tk.Toplevel))
    text_widgets = [w for w in dialog.winfo_children() if isinstance(w, tk.Text)]
    check("dialog has its own independent Text widget", len(text_widgets) == 1)
    text_widgets[0].insert("1.0", "x = 5\n")
    check("dialog's text widget is independent of self.code_text",
          "x = 5" not in app.code_text.get(1.0, tk.END))
    dialog.destroy()

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll Nodes-layer code-toggle / panel-visibility assertions passed.")


if __name__ == "__main__":
    main()
