"""
Scripted UI test (run under Xvfb): the UI designer inside the full app.

A safety net for the designer refactor (B1-B3): it records what the
designer does today through the app's own methods - open a UI node, add
a widget, set a property, undo/redo, detach, reattach, save, reload - so a
move of the Tk code can be checked against it. Nothing here reaches into
the designer's widgets; it asserts on the document and on app state.

Run it repeatedly (xvfb-run -a python3 tests/test_designer_smoke.py).
Not a pytest file - run directly, same convention as the other tests.
"""
import os
import sys
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import project_file
import ui_node
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(3):
        app.update_idletasks()
        app.update()


def widgets(tree):
    root_id = tree.root["id"]
    return [w for w in tree.walk() if w["id"] != root_id]


def main():
    # Dialogs must never block the run.
    messagebox.askyesno = lambda *a, **k: True
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]
        pack = app.ui_pack_for(tab["language"])
        check("python has a UI pack", pack is not None)
        if pack is None:
            return

        node = app.create_starter_node("ui", (80, 80))
        settle(app)
        check("a UI node was created", node is not None and ui_node.is_ui_node(node))
        app.open_node(node["id"])
        settle(app)

        check("the designer shows for an attached UI node", app.designer_node() is node)
        check("the workspace is locked for the designer", getattr(app, "_workspace_locked", False) is True)
        check("the designer drew its frame", app._dz_root.winfo_exists())

        # add a widget
        tree = ui_node.load_tree(node, pack)
        before = len(widgets(tree))
        app._dz_add_type("button")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        added = widgets(tree)
        check("adding a button adds one widget", len(added) == before + 1)
        wid = app._dz()["sel"]
        check("the new widget is selected", wid is not None and tree.find(wid) is not None)
        check("the tab is marked dirty", tab_dirty(app))
        check("generated code mentions the widget",
              any(w["name"] in code_of(app, node) for w in added))

        # set a property
        app._dz_set_prop(wid, {"key": "text"}, "Smoke")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("the property is stored", tree.find(wid)["props"].get("text") == "Smoke")
        check("the code follows the property", "Smoke" in code_of(app, node))

        # undo / redo
        app._dz_undo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("undo restores the property", tree.find(wid)["props"].get("text") != "Smoke")
        app._dz_redo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("redo brings it back", tree.find(wid)["props"].get("text") == "Smoke")

        # undo survives a refresh of the workspace
        app.refresh_workspace()
        settle(app)
        app._dz_undo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("undo still works after a refresh", tree.find(wid)["props"].get("text") != "Smoke")
        app._dz_redo()
        settle(app)

        # rename
        app._dz_rename(wid, "btn_smoke")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("rename is stored", tree.find(wid)["name"] == "btn_smoke")

        # a new event handler is a new function node next to the UI node
        count = len(list(app.iter_tab_nodes(app.tabs[app.active_tab_index])))
        handler_id = app._dz_new_handler("btn_smoke", "command")
        names = {n["name"]: n for n, _p in app.iter_tab_nodes(app.tabs[app.active_tab_index])}
        check("a handler node was added", len(names) == count + 1 and "on_btn_smoke_command" in names)
        check("the id points at it", names["on_btn_smoke_command"]["id"] == handler_id)

        # save and reload (pure round trip of the open workspace)
        app.sync_active_tab_state()
        ws = app.workspaces[app.active_ws_index]
        data = project_file.build_workspace_data(ws["files"], ws["active_index"])
        check("the save is typed", data.get("type") == "codebuilder.workspace")
        files, _ai, _notes = project_file.parse_workspace_data(data, ["python"], "python")
        again = next((n for n in files[0]["nodes"] if ui_node.is_ui_node(n)), None)
        check("the UI node survives a save and reload", again is not None)
        if again is not None:
            reloaded = ui_node.load_tree(again, pack)
            check("its widgets survive", reloaded is not None
                  and reloaded.find(wid) is not None and reloaded.find(wid)["name"] == "btn_smoke")
            check("still attached after reload", not ui_node.is_detached(again))

        # detach / reattach
        app._dz_detach()
        settle(app)
        check("detached: the designer no longer shows", app.designer_node() is None)
        check("detached: the workspace is unlocked", getattr(app, "_workspace_locked", False) is False)
        check("detached: the node says so", ui_node.is_detached(node))
        app.reattach_ui_node()
        settle(app)
        check("reattached: the designer shows again", app.designer_node() is node)
        check("reattached: the widget is still there",
              ui_node.load_tree(node, pack).find(wid) is not None)

        # leave the node: the lock goes away
        app.switch_to_file_view()
        settle(app)
        check("leaving the node unlocks the workspace", getattr(app, "_workspace_locked", False) is False)
    finally:
        app.destroy()

    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)


def tab_dirty(app):
    return bool(app.tabs[app.active_tab_index].get("dirty"))


def code_of(app, node):
    tab = app.tabs[app.active_tab_index]
    text = app._dz_code_text(tab, node)
    return text if text is not None else str(node.get("blocks"))


if __name__ == "__main__":
    main()
