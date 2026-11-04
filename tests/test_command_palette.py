"""
Scripted UI test (run under Xvfb): menus come from the command registry, the
palette finds and runs commands, and extension commands join and leave.
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def labels(menu):
    return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) in ("command", "cascade")]


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None
    app.geometry("1200x800")
    app.update()
    reg = app.command_registry

    ids = {c.id for c in reg.all()}
    check("the app's commands are registered", {"file.save", "file.undo", "run.run", "tools.palette", "help.about"} <= ids)
    check("File menu is drawn from the registry", labels(app.topbar_menus["File"])[:3] == ["Undo", "Redo", "Save"])
    check("the burger menu shows the same entries",
          labels(app._burger_subs["File"])[:3] == ["Undo", "Redo", "Save"])

    called = []
    app.save_project = lambda: called.append("save")
    check("running a command by id reaches the current method", reg.run("file.save") and called == ["save"])

    # the palette
    win = app.show_command_palette()
    app.update()
    check("the palette opens", win.winfo_exists())
    check("opening it again reuses the window", app.show_command_palette() is win)
    entry = next(w for w in walk(win) if w.winfo_class() == "Entry")
    box = next(w for w in walk(win) if w.winfo_class() == "Listbox")
    check("an empty search lists the commands", box.size() >= len(ids) - 5)
    entry.insert(0, "sav")
    app.update()
    check("typing narrows the list; Save comes first", box.size() >= 1 and "Save" in box.get(0))
    called.clear()
    entry.event_generate("<Return>")
    app.update()
    app.after(100, lambda: None)
    for _ in range(5):
        app.update()
    check("Enter runs the chosen command and closes the palette", called == ["save"] and not win.winfo_exists())

    app.show_command_palette()
    app.update()
    win2 = app._palette_win
    win2.event_generate("<Escape>")
    app.update()
    check("Escape closes it", not win2.winfo_exists())

    # extensions' commands
    ext = [e for e in app._ext_all if e["manifest"]["commands"]]
    if ext:
        m = ext[0]["manifest"]
        cmd = m["commands"][0]
        cid = f"ext:{m['id']}:{cmd['command']}"
        active = reg.get(cid) is not None
        check("an enabled extension's command is in the registry", active or not ext[0])
        if active:
            check("and in the menu it named", cmd["label"] in labels(app.topbar_menus[cmd["menu"]]) or cmd["menu"] not in app.topbar_menus)
        before = len(reg.all())
        reg.unregister_owner(m["id"])
        app.refresh_topbar_menus()
        check("taking an extension's commands away removes them from the menu",
              cmd["label"] not in labels(app.topbar_menus.get(cmd["menu"], app.topbar_menus["Tools"])) and len(reg.all()) <= before)
        app.sync_extension_commands()
        check("syncing brings the active ones back", reg.get(cid) is not None or not active)

    app.destroy()
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
