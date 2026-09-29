"""The FocusOut commit's destructive rebuild is deferred to after_idle
(Handoff #4's real-desktop caveat: clicking straight from one edited
code box into another could have its click/caret swallowed because the
old synchronous version destroyed every widget, including the one just
clicked into, inside the very FocusOut triggered by that click)."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI, make_node

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def text_widgets(app):
    return [w for w in app.workspace_frame.winfo_children() if isinstance(w, tk.Text)]

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    tab = app.tabs[0]
    node_a = make_node("NodeA", node_id="a1", blocks=[("assign_variable", {"variable": "x", "value": "1"})])
    node_b = make_node("NodeB", node_id="b1", blocks=[("assign_variable", {"variable": "y", "value": "2"})])
    tab["nodes"] = [node_a, node_b]
    tab["active_node_id"] = node_a["id"]
    app.project_blocks = node_a["blocks"]
    app.switch_to_file_view()
    app.toggle_file_view_code_mode()
    app.update()

    widgets = text_widgets(app)
    check("two editable boxes to start", len(widgets) == 2)
    box_a_before = widgets[0]

    # Edit NodeA, then fire the same FocusOut the real widget binding
    # fires when focus leaves it (e.g. by clicking into NodeB's box).
    widgets[0].delete("1.0", tk.END)
    widgets[0].insert("1.0", "x = 1\nz = 9\n")
    app._on_node_code_focus_out(node_a, widgets[0])

    # --- The critical property: nothing destructive happened yet. ---
    check("commit returns without destroying widgets synchronously",
          box_a_before.winfo_exists() and len(text_widgets(app)) == 2)
    check("the data mutation itself is ALSO deferred (blocks unchanged so far)",
          node_a["blocks"] == [("assign_variable", {"variable": "x", "value": "1"})])
    check("a pending idle callback is queued", bool(app.tk.eval('after info')))

    # Simulate the rest of the click: focus actually lands on NodeB's
    # box. This must survive the deferred rebuild that's about to run.
    widgets[1].focus_set()

    # Now let the event loop run one idle pass - this is what actually
    # happens between real mouse-click events on a live desktop.
    app.update()

    check("after idle: NodeA's blocks are now updated", len(node_a["blocks"]) == 2
          and node_a["blocks"][1] == ("assign_variable", {"variable": "z", "value": "9"}))
    check("the old NodeA widget was replaced by the rebuild", not box_a_before.winfo_exists())
    rebuilt = text_widgets(app)
    check("still exactly two boxes after the deferred rebuild", len(rebuilt) == 2)
    check("rebuilt NodeA box shows the committed text", "z = 9" in rebuilt[0].get("1.0", tk.END))
    check("NodeB's box (the click target) still exists with its own text",
          "y = 2" in rebuilt[1].get("1.0", tk.END))

    # --- No-op edits must not even queue a deferred callback. ---
    before = app.tk.eval('after info')
    app._on_node_code_focus_out(node_a, text_widgets(app)[0])
    check("unchanged text queues nothing", app.tk.eval('after info') == before)

    # --- Guard re-checked at apply time: if the node is deleted (or the
    # tab is switched away from) between the click and the idle tick,
    # the deferred callback must still be a safe no-op. ---
    widgets2 = text_widgets(app)
    widgets2[1].delete("1.0", tk.END)
    widgets2[1].insert("1.0", "y = 2\nw = 5\n")
    app._on_node_code_focus_out(node_b, widgets2[1])
    check("deferred callback queued for the NodeB edit", node_b["blocks"] == [("assign_variable", {"variable": "y", "value": "2"})])
    tab["nodes"].remove(node_b)   # node vanishes before the idle tick fires
    app.update()
    check("node deleted before the idle tick fires: deferred commit is a safe no-op, no crash",
          True)
    check("no stray blocks were written back onto the removed node",
          node_b["blocks"] == [("assign_variable", {"variable": "y", "value": "2"})])

    # --- Re-entrancy: while a deferred commit is applying (inside
    # refresh_workspace's rebuild), a second FocusOut on a now-dead
    # widget must not double-commit or crash. ---
    tab["nodes"] = [node_a]
    tab["active_node_id"] = node_a["id"]
    app.refresh_workspace(); app.update()
    w = text_widgets(app)[0]
    w.delete("1.0", tk.END); w.insert("1.0", "x = 1\nq = 1\n")
    app._on_node_code_focus_out(node_a, w)
    app._node_code_committing = True   # simulate being mid-apply
    app._on_node_code_focus_out(node_a, w)
    app._node_code_committing = False
    app.update()
    check("re-entrant call during an in-flight commit doesn't crash or double-apply",
          len(node_a["blocks"]) == 2)

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All deferred-commit tests passed.")

main()
