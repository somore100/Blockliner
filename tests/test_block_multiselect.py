"""Scripted UI test (run under Xvfb): Ctrl/Shift+click picks several blocks and
"Group into node..." moves them into a new node that runs right after the original."""
import os
import sys
from tkinter import messagebox, simpledialog

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes_model import sorted_function_nodes
from ui import BlocklinerUI

FAILURES = []
CTRL, SHIFT = 0x4, 0x1


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(4):
        app.update_idletasks()
        app.update()


def values(blocks):
    return [p.get("text") for _b, p in blocks]


def main():
    shown = []
    messagebox.showinfo = lambda *a, **k: shown.append(a)
    simpledialog.askstring = lambda *a, **k: "Middle part"
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900")
    try:
        settle(app)
        app.goto_layer("blocks")
        tab = app.tabs[app.active_tab_index]
        node = app.get_active_node(tab)
        del app.project_blocks[:]
        app.project_blocks.extend(("comment", {"text": t}) for t in "abcde")
        app.refresh_workspace()
        settle(app)
        lst = app.project_blocks

        app.select_block(1, lst)
        check("a plain click selects one block and shows no bar", app.is_block_selected(1, lst) and app._multi_bar is None)
        app.select_block(2, lst, state=CTRL)
        check("ctrl+click adds the second", app.is_block_selected(1, lst) and app.is_block_selected(2, lst))
        check("the bar appears with two or more", app._multi_bar is not None and "2 blocks" in app._multi_label.cget("text"))
        app.select_block(2, lst, state=CTRL)
        check("ctrl+click again removes it and the bar goes", not app.is_block_selected(2, lst) and app._multi_bar is None)
        app.select_block(1, lst)
        app.select_block(3, lst, state=SHIFT)
        check("shift+click after a plain click takes the range", all(app.is_block_selected(i, lst) for i in (1, 2, 3)))
        app.select_block(2, lst, state=SHIFT)
        check("shift+click on a picked block drops it", not app.is_block_selected(2, lst) and app.is_block_selected(3, lst))
        app.select_block(2, lst, state=SHIFT)
        check("shift+click on a dropped block starts a new section", app.is_block_selected(2, lst) and app._block_pending == 2)
        app.select_block(4, lst, state=SHIFT)
        check("the next shift+click picks up to it", all(app.is_block_selected(i, lst) for i in (1, 2, 3, 4)))

        app.settings["block_select_mode"] = "single"
        app.clear_block_multi_selection()
        app.select_block(0, lst)
        app.select_block(3, lst)
        check("single mode: plain clicks add up", app.is_block_selected(0, lst) and app.is_block_selected(3, lst)
              and not app.is_block_selected(1, lst))
        app.select_block(0, lst)
        check("single mode: a click on a picked block drops it", not app.is_block_selected(0, lst))

        app.settings["block_select_mode"] = "range"
        app.clear_block_multi_selection()
        app.select_block(1, lst)
        app.select_block(3, lst)
        check("range mode: first then last picks everything between", all(app.is_block_selected(i, lst) for i in (1, 2, 3)))
        app.settings["block_select_mode"] = "shift"
        app.clear_block_multi_selection()
        app.select_block(1, lst)
        app.select_block(3, lst, state=SHIFT)

        node_count = len(tab["nodes"])
        app.make_node_from_selection()
        settle(app)
        names = [n["name"] for n in sorted_function_nodes(tab["nodes"])]
        check("two new nodes appeared", len(tab["nodes"]) == node_count + 2)
        check("they run right after the original, in order", names[:3] == [node["name"], "Middle part", f"{node['name']} (rest)"])
        check("the original keeps what came before", values(node["blocks"]) == ["a"])
        by_name = {n["name"]: n for n in tab["nodes"]}
        check("the new node holds the picked blocks", values(by_name["Middle part"]["blocks"]) == ["b", "c", "d"])
        check("the tail went to the rest node", values(by_name[f"{node['name']} (rest)"]["blocks"]) == ["e"])
        check("the selection and bar are gone", app._multi_bar is None and not app.block_multi_selection())
        check("the open list is still the node's own list", app.project_blocks is node["blocks"])
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
