"""
Scripted UI test (run under Xvfb): the designer editor on its own - a bare Tk
window as host and an in-memory document as port, no BlocklinerUI.

Proves the editor depends only on the host/port interfaces. Run with
xvfb-run -a python3 tests/test_designer_standalone.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_pack
from designer_editor import UIDesignerEditor
from designer_port import UIDocumentPort
from ui_tree import UITree

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


class MemoryPort(UIDocumentPort):
    def __init__(self, pack):
        self._pack = pack
        tree = UITree.new(pack.id, root_type="window", root_name="root", props=pack.defaults("window"),
                          is_container=pack.is_container)
        self.doc = tree.to_dict()
        self.handlers = []          # (name, id)
        self.detached = False
        self.dirty = 0
        self.regenerated = 0

    def key(self): return "doc"
    def pack(self): return self._pack
    def stored(self): return self.doc
    def load_tree(self): return UITree.from_dict(self.doc, is_container=self._pack.is_container)
    def store_tree(self, tree): self.doc = tree.to_dict()
    def handler_targets(self): return [(n, i, False) for n, i in self.handlers]

    def create_handler(self, widget_name, event_key):
        hid = f"h{len(self.handlers) + 1}"
        self.handlers.append((f"on_{widget_name}_{event_key}", hid))
        return hid

    def detach(self): self.detached = True
    def preview_source(self): return None, ["no preview in this test"]
    def regenerate(self): self.regenerated += 1
    def mark_dirty(self): self.dirty += 1


class BareHost:
    def __init__(self, root):
        self.root = root
        self.frame = tk.Frame(root, width=900, height=600)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.editor = None
        self.port = None
        self.refreshes = 0

    def after(self, ms, func=None, *a): return self.root.after(ms, func, *a)
    def after_idle(self, func, *a): return self.root.after_idle(func, *a)
    def bell(self): pass
    def winfo_rgb(self, colour): return self.root.winfo_rgb(colour)
    def view_width(self): return 900

    def refresh(self):
        self.refreshes += 1
        for w in self.frame.winfo_children():
            w.destroy()
        if self.showing():
            self.editor.render_designer()

    def showing(self): return not self.port.detached


def settle(root):
    for _ in range(3):
        root.update_idletasks()
        root.update()


def widgets(port):
    t = port.load_tree()
    return [w for w in t.walk() if w["id"] != t.root["id"]]


def main():
    pack = ui_pack.find_packs([os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui_packs")],
                              "python")[0][0]
    root = tk.Tk()
    try:
        host = BareHost(root)
        port = MemoryPort(pack)
        host.port = port
        editor = UIDesignerEditor(host, port)
        host.editor = editor

        editor.render_designer()
        settle(root)
        check("the editor drew into the host's frame", editor._dz_root.winfo_exists() and editor._dz_root.master is host.frame)

        editor._dz_add_type("button")
        settle(root)
        added = widgets(port)
        check("adding a widget changes the document", len(added) == 1)
        wid = editor.state["sel"]
        check("the new widget is selected", wid == added[0]["id"])
        check("the port was told", port.dirty >= 1 and port.regenerated >= 1)

        editor._dz_set_prop(wid, {"key": "text"}, "Hi")
        settle(root)
        check("a property is stored in the document", port.load_tree().find(wid)["props"].get("text") == "Hi")

        editor._dz_undo()
        settle(root)
        check("undo", port.load_tree().find(wid)["props"].get("text") != "Hi")
        editor._dz_redo()
        settle(root)
        check("redo", port.load_tree().find(wid)["props"].get("text") == "Hi")

        editor._dz_rename(wid, "btn_hi")
        settle(root)
        check("rename", port.load_tree().find(wid)["name"] == "btn_hi")

        hid = editor._dz_new_handler("btn_hi", "command")
        check("a new handler comes from the port", port.handlers == [("on_btn_hi_command", hid)])
        check("handlers are offered as event targets", editor._dz_function_names() == [("on_btn_hi_command", hid)])

        editor._dz_remove()
        settle(root)
        check("remove", widgets(port) == [])

        before = port.dirty
        editor._dz_detach()
        settle(root)
        check("detach goes through the port", port.detached and port.dirty > before)
        check("the editor forgot its state", "tree" not in editor.state)
        check("the host was asked to refresh", host.refreshes >= 1)
    finally:
        root.destroy()

    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
