"""Lazy block rendering (Blocks layer): only a window of top-level blocks is
built as widgets; footer / auto-load / reveal keep every edit flow working.
Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
from tkinter import ttk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import BlocklinerUI, make_node, normalize_orders
from ui_common import BLOCK_CHUNK
from ui_widgets import BlockWidget

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def assign(i): return ("assign_variable", {"variable": f"v{i}", "value": str(i)})

def widgets(app):
    return [w for w in app.workspace_frame.winfo_children() if isinstance(w, BlockWidget)]

def label_text(app): return str(app.block_count_label.cget("text"))

def open_node(app, tab, node):
    tab["active_node_id"] = node["id"]; app.project_blocks = node["blocks"]
    app.view_mode = "node"; app.refresh_workspace(); app.update()

def find_buttons(root, text):
    out = []
    for w in root.winfo_children():
        if isinstance(w, (tk.Button, ttk.Button)) and str(w.cget("text")).startswith(text): out.append(w)
        out += find_buttons(w, text)
    return out

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()
    ui.messagebox.askyesno = lambda *a, **k: True
    tab = app.tabs[0]
    small = make_node("small", node_id="s", blocks=[assign(i) for i in range(10)])
    big = make_node("big", node_id="b", blocks=[assign(i) for i in range(150)])
    tab["nodes"] = [small, big]; tab["file_view_path"] = []; normalize_orders(tab["nodes"])
    n = BLOCK_CHUNK

    # ---- small node: nothing changes ----
    open_node(app, tab, small)
    check("small node: all 10 widgets, no footer", len(widgets(app)) == 10 and app._more_footer is None)
    check("small node: label unchanged", label_text(app) == "10 blocks")

    # ---- big node: windowed ----
    open_node(app, tab, big)
    check(f"big node: only {n} widgets built", len(widgets(app)) == n)
    check("footer present", app._more_footer is not None and app._more_footer.winfo_exists())
    check("label shows window", label_text(app) == f"150 blocks (showing 1-{n})")
    check("generated code still contains ALL blocks", "v149 = 149" in app.generate_code_for_tab(tab, "python"))

    # ---- show more, in place ----
    first = widgets(app)[0]
    app._show_more_blocks(); app.update()
    check(f"show next: {2*n} widgets", len(widgets(app)) == 2 * n)
    check("show next is in place (existing widget kept)", first.winfo_exists() and widgets(app)[0] is first)
    check("widget indexes are absolute and in order", [w.index for w in widgets(app)] == list(range(2 * n)))
    check("footer text updated", "30 more" in str([c.cget("text") for c in app._more_footer.winfo_children() if isinstance(c, tk.Label)]))

    # ---- window persists across refreshes of the same list ----
    big["blocks"][100] = ("assign_variable", {"variable": "edited", "value": "1"})
    app.refresh_workspace(); app.update()
    check("window persists across refresh (editing block 100)", len(widgets(app)) == 2 * n)

    app._show_more_blocks(all_remaining=True); app.update()
    check("show all: 150 widgets, footer gone", len(widgets(app)) == 150 and app._more_footer is None)
    check("label back to plain", label_text(app) == "150 blocks")

    # ---- switching node resets window ----
    open_node(app, tab, small); open_node(app, tab, big)
    check("reopen big node: window reset to first chunk", len(widgets(app)) == n)

    # ---- auto-load on scroll to bottom ----
    app.update(); app.workspace_canvas.yview_moveto(1.0); app.update(); app.update()
    check("scrolling to the bottom auto-loads the next chunk", len(widgets(app)) > n)
    check("auto-load did not cascade through everything", len(widgets(app)) <= 3 * n)

    # ---- add flow while viewing top of a windowed node: new block must be visible ----
    open_node(app, tab, big)
    app.edit_block_params(app.blocks["assign_variable"], {"variable": "newest", "value": "9"}, add_mode=True)
    dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    btn = find_buttons(dlg, "Save & Add")
    btn[0].invoke(); app.update()
    check("append adds the block to the data", big["blocks"][-1][1]["variable"] == "newest" and len(big["blocks"]) == 151)
    check("append from top: window jumps to tail so new block is built", any(w.index == 150 for w in widgets(app)))
    check("tail window is bounded", len(widgets(app)) <= n)
    check("earlier-blocks row shown", app._earlier_row.winfo_exists())
    start = app._win_start
    app._show_earlier_blocks(); app.update()
    check("show earlier lowers window start", app._win_start == max(0, start - n))
    check("generated code has the new block", "newest = 9" in app.generate_code_for_tab(tab, "python"))

    # ---- move at the window edge pulls the neighbour in ----
    open_node(app, tab, small); open_node(app, tab, big)
    last_idx = n - 1
    app.move_block_down(last_idx); app.update()
    check("move down past window edge: moved block still visible", any(w.index == last_idx + 1 for w in widgets(app)))
    check("data swapped correctly", big["blocks"][last_idx + 1][1]["variable"] == f"v{last_idx}")

    # ---- delete inside window keeps window ----
    open_node(app, tab, small); open_node(app, tab, big)
    app.delete_block(0); app.update()
    check("delete in window: still a full chunk, footer says remaining", len(widgets(app)) == n and app._more_footer is not None)

    # ---- appends that bypass the dialog (e.g. code import) while viewing the tail ----
    open_node(app, tab, small); open_node(app, tab, big)
    app._show_more_blocks(all_remaining=True); app.update()
    nb = len(big["blocks"]); big["blocks"].append(assign(999)); app.refresh_workspace(); app.update()
    check("append while viewing the tail: new block joins the window", any(w.index == nb for w in widgets(app)))

    # ---- window shrunk away entirely falls back to the tail chunk ----
    open_node(app, tab, small); open_node(app, tab, big)
    app.reveal_block(0, to_tail=True); app.refresh_workspace(); app.update()
    ws, we = app._win_start, app._win_end
    del big["blocks"][ws:]          # everything the window showed disappears
    app.refresh_workspace(); app.update()
    check("window past the end falls back to a tail chunk", len(widgets(app)) > 0 and widgets(app)[-1].index == len(big["blocks"]) - 1)

    # ---- delete everything in a window clamps instead of crashing ----
    tiny = make_node("tiny", node_id="t", blocks=[assign(i) for i in range(3)])
    tab["nodes"].append(tiny); open_node(app, tab, tiny)
    for _ in range(3): app.delete_block(0)
    app.update()
    check("deleting every block shows empty state", len(widgets(app)) == 0 and app.empty_label.winfo_exists())
    app.project_blocks.append(assign(1)); app.refresh_workspace(); app.update()
    check("adding after empty renders it", len(widgets(app)) == 1)

    # ---- collapsed container via toggle keeps window ----
    open_node(app, tab, big)
    app._show_more_blocks(); app.update(); k = len(widgets(app))
    widgets(app)[0].toggle_collapsed(); app.update()
    check("toggle_collapsed refresh keeps window size", len(widgets(app)) == k)

    app.destroy()
    print(); print("FAILED: " + ", ".join(FAILURES) if FAILURES else "ALL OK")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
