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
        check("the designer has its own frame, not the scrolling canvas",
              shows_editor(app) and app.current_editor() is not None and app.current_editor().id == "ui-designer")
        check("the designer drew its frame", app.designer_editor._dz_root.winfo_exists())

        # add a widget
        tree = ui_node.load_tree(node, pack)
        before = len(widgets(tree))
        app.designer_editor._dz_add_type("button")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        added = widgets(tree)
        check("adding a button adds one widget", len(added) == before + 1)
        wid = app.designer_editor.state["sel"]
        trace(app, node, pack, "added a widget")
        check("the new widget is selected", wid is not None and tree.find(wid) is not None)
        check("the tab is marked dirty", tab_dirty(app))
        check("generated code mentions the widget",
              any(w["name"] in code_of(app, node) for w in added))

        # set a property
        app.designer_editor._dz_set_prop(wid, {"key": "text"}, "Smoke")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("the property is stored", tree.find(wid)["props"].get("text") == "Smoke")
        check("the code follows the property", "Smoke" in code_of(app, node))
        trace(app, node, pack, "set property")

        # undo / redo
        app.designer_editor._dz_undo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("undo restores the property", tree.find(wid)["props"].get("text") != "Smoke")
        app.designer_editor._dz_redo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("redo brings it back", tree.find(wid)["props"].get("text") == "Smoke")
        trace(app, node, pack, "undo+redo")

        # undo survives a refresh of the workspace
        app.refresh_workspace()
        settle(app)
        app.designer_editor._dz_undo()
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("undo still works after a refresh", tree.find(wid)["props"].get("text") != "Smoke")
        app.designer_editor._dz_redo()
        settle(app)
        trace(app, node, pack, "refresh, undo, redo")

        # rename
        app.designer_editor._dz_rename(wid, "btn_smoke")
        settle(app)
        tree = ui_node.load_tree(node, pack)
        check("rename is stored", tree.find(wid)["name"] == "btn_smoke")
        trace(app, node, pack, "rename")

        # a new event handler is a new function node next to the UI node
        count = len(list(app.iter_tab_nodes(app.tabs[app.active_tab_index])))
        handler_id = app.designer_editor._dz_new_handler("btn_smoke", "command")
        names = {n["name"]: n for n, _p in app.iter_tab_nodes(app.tabs[app.active_tab_index])}
        check("a handler node was added", len(names) == count + 1 and "on_btn_smoke_command" in names)
        check("the id points at it", names["on_btn_smoke_command"]["id"] == handler_id)
        trace(app, node, pack, "new handler")

        # save and reload (pure round trip of the open workspace)
        app.sync_active_tab_state()
        ws = app.workspaces[app.active_ws_index]
        data = project_file.build_workspace_data(ws["files"], ws["active_index"])
        check("the save is typed", data.get("type") == "codebuilder.workspace")
        trace(app, node, pack, "sync+build save data")
        files, _ai, _notes = project_file.parse_workspace_data(data, ["python"], "python")
        again = next((n for n in files[0]["nodes"] if ui_node.is_ui_node(n)), None)
        check("the UI node survives a save and reload", again is not None)
        if again is not None:
            reloaded = ui_node.load_tree(again, pack)
            check("its widgets survive", reloaded is not None
                  and reloaded.find(wid) is not None and reloaded.find(wid)["name"] == "btn_smoke")
            check("still attached after reload", not ui_node.is_detached(again))

        # detach / reattach
        pre = ([w["name"] for w in widgets(ui_node.load_tree(node, pack))], code_of(app, node))
        app.designer_editor._dz_detach()
        settle(app)
        post = ([w["name"] for w in widgets(ui_node.load_tree(node, pack))], code_of(app, node))
        check("detached: the designer no longer shows", app.designer_node() is None)
        check("detached: the scrolling canvas is back", not shows_editor(app) and app.current_editor() is None)
        check("detached: the node says so", ui_node.is_detached(node))
        app.reattach_ui_node()
        settle(app)
        check("reattached: the designer shows again", app.designer_node() is node)
        # reading the code back gives widgets new ids; their names are what carries over
        names_now = [w["name"] for w in widgets(ui_node.load_tree(node, pack))]
        check("reattached: the widget is still there (by name)", "btn_smoke" in names_now)
        if "btn_smoke" not in names_now:       # diagnostics for a failing run
            print("  widgets now:", names_now)
            print("  detached:", ui_node.is_detached(node))
            print("  trace:")
            for line in TRACE:
                print("   ", line)
            print("  code before detach:\n" + pre[1])
            print("  before detach: widgets", pre[0], "| has button in code:", "btn_smoke" in pre[1])
            print("  after detach:  widgets", post[0], "| has button in code:", "btn_smoke" in post[1])
            print("  code:\n" + code_of(app, node))

        # leave the node: the lock goes away
        app.switch_to_file_view()
        settle(app)
        check("leaving the node brings the canvas back", not shows_editor(app))
    finally:
        app.destroy()

    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)


TRACE = []


def trace(app, node, pack, label):
    """One line per step: the node's widget names and whether the code has them."""
    names = [w["name"] for w in widgets(ui_node.load_tree(node, pack))]
    code = code_of(app, node)
    TRACE.append(f"{label}: widgets={names} code_has_all={all(n in code for n in names)} "
                 f"code_lines={len(code.splitlines())}")


def shows_editor(app):
    """The editor frame is on screen and the canvas is not."""
    return bool(app.editor_frame.winfo_ismapped()) and not app.workspace_canvas.winfo_ismapped()


def tab_dirty(app):
    return bool(app.tabs[app.active_tab_index].get("dirty"))


def code_of(app, node):
    text = app.cb.raw_code_text(node)
    return text if text is not None else str(node.get("blocks"))


if __name__ == "__main__":
    main()
