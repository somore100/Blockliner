"""
Scripted UI test (run under Xvfb): the depot window lists packages and installs
one, leaving it switched off.
"""
import json
import os
import sys
import tempfile
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def main():
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    with tempfile.TemporaryDirectory() as tmp:
        depot_dir, user_root = os.path.join(tmp, "depot"), os.path.join(tmp, "extensions")
        pkg = os.path.join(depot_dir, "tool")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "extension.json"), "w") as f:
            json.dump({"format": "blockliner-extension", "version": 1, "id": "acme/tool", "name": "Acme Tool",
                       "extension_version": "1.0.0", "requires": {"api": "1.0"}, "permissions": ["project.read"],
                       "enabled_by_default": True}, f)

        app = BlocklinerUI(initial_lang="python", languages_path="languages")
        app.save_app_settings = lambda: None
        app.geometry("1200x800")
        app.update()
        roots = app.extension_roots()
        app.extension_roots = lambda: [roots[0], (user_root, "user")]
        app.depot_dir = lambda: depot_dir

        win = app.show_depot()
        app.update()
        table = next(w for w in walk(win) if w.winfo_class() == "Treeview")
        check("the package is listed", len(table.get_children()) == 1 and "Acme Tool" in table.item("0", "values"))
        check("it shows as not installed", "Not installed" in table.item("0", "values"))
        install = next(w for w in walk(win) if w.winfo_class() == "Button" and w.cget("text") in ("Install", "Update"))
        check("Install is available", str(install.cget("state")) == "normal")

        install.invoke()
        app.update()
        check("it was copied into the extensions folder", os.path.isfile(os.path.join(user_root, "acme-tool", "extension.json")))
        check("it is switched off, even though its manifest says on by default",
              app.settings.get("extensions_enabled", {}).get("acme/tool") is False)
        check("the app knows it now", any(e["manifest"] and e["manifest"]["id"] == "acme/tool" for e in app._ext_all))
        check("the list now says Installed", "Installed" in table.item("0", "values"))
        check("Install is no longer offered", str(install.cget("state")) == "disabled")
        app.destroy()

    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
