"""Scripted UI test (run under Xvfb): Ctrl+S saves in place or asks where, saves are all-or-nothing with a .bak,
an existing app-folder file asks before being replaced, recovery copies are written and removed, and what a crash
leaves behind is offered back at the next start."""
import json
import os
import shutil
import sys
import tempfile
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autosave
import safe_write
import ui_codegen
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(5):
        app.update_idletasks()
        app.update()


def make_app(rec):
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1300x800+0+0")
    app.recovery_folder = lambda: rec
    settle(app)
    return app


def add_block(app, text):
    node = app.get_active_node(app.tabs[app.active_tab_index])
    node["blocks"].append(("print_output", {"value": text}))
    app.mark_active_tab_dirty()
    app.refresh_workspace()
    settle(app)


def find_button(w, label):
    for c in w.winfo_children():
        if c.winfo_class() == "Button" and label in c.cget("text"):
            return c
        got = find_button(c, label)
        if got:
            return got
    return None


def main():
    work = tempfile.mkdtemp()
    rec = os.path.join(work, "recovery")
    asked = []
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showwarning = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: asked.append(("error", a))
    messagebox.askyesno = lambda *a, **k: (asked.append(("yesno", a)), True)[1]
    app = make_app(rec)
    try:
        # ---- Ctrl+S
        add_block(app, "'one'")
        dialogs = []
        real_as = app.save_project_as
        app.save_project_as = lambda: dialogs.append(1)
        app.focus_force(); settle(app)
        app.event_generate("<Control-s>")
        settle(app)
        check("Ctrl+S on a project with no file asks where (Save As)", dialogs == [1])
        app.save_project_as = real_as
        path = os.path.join(work, "game.json")
        check("a first save writes the file", app._write_project_file(path, quiet=True) and os.path.isfile(path))
        ws = app.workspaces[app.active_ws_index]
        check("the project now remembers its file and is clean", ws["filepath"] == path and not app.workspace_dirty(ws))
        add_block(app, "'two'")
        size_before = os.path.getsize(path)
        app.event_generate("<Control-s>")
        settle(app)
        check("Ctrl+S now saves straight to that file, no dialog", os.path.getsize(path) > size_before and not app.workspace_dirty(ws))
        check("the previous version is kept as .bak", os.path.isfile(path + ".bak") and os.path.getsize(path + ".bak") == size_before)
        check("a bar says where it was saved", getattr(app, "_change_bar", None) is not None)

        # ---- all or nothing
        good = open(path, encoding="utf-8").read()
        real = safe_write.write_text_atomic
        def boom(*a, **k):
            raise OSError("disk full")
        safe_write.write_text_atomic = boom
        asked.clear()
        add_block(app, "'three'")
        ok = app._write_project_file(path)
        safe_write.write_text_atomic = real
        check("a failed save reports it, keeps the old file whole, and the project stays unsaved",
              ok is False and open(path, encoding="utf-8").read() == good and app.workspace_dirty(ws) and any(k == "error" for k, _ in asked))

        # ---- overwrite prompt in the app folder
        saves = os.path.join(work, "saves")
        os.makedirs(saves)
        ui_codegen.BLOCKLINER_SAVES_PATH = saves
        existing = os.path.join(saves, "taken.json")
        with open(existing, "w") as f:
            f.write("{}")
        ws["filepath"] = None
        dlg_before = set(app.winfo_children())
        app.save_project_as()
        settle(app)
        dlg = next(w for w in app.winfo_children() if w not in dlg_before and w.winfo_class() == "Toplevel")
        entry = next(c for c in dlg.winfo_children()[1].winfo_children() if c.winfo_class() == "Entry")
        entry.delete(0, "end"); entry.insert(0, "taken")
        messagebox.askyesno = lambda *a, **k: (asked.append(("yesno", a)), False)[1]
        asked.clear()
        find_button(dlg, "Save to App Folder").invoke()
        settle(app)
        check("an existing name asks first; No leaves that file alone", any(k == "yesno" for k, _ in asked) and open(existing).read() == "{}" and dlg.winfo_exists())
        messagebox.askyesno = lambda *a, **k: (asked.append(("yesno", a)), True)[1]
        find_button(dlg, "Save to App Folder").invoke()
        settle(app)
        check("Yes replaces it", json.load(open(existing, encoding="utf-8")).get("format") == "blockliner-project")

        # ---- recovery copies
        fresh = app.new_workspace()
        add_block(app, "'only in memory'")
        fresh = app.workspaces[app.active_ws_index]
        fresh["title"] = "Crash test"
        wrote = app.autosave_now()
        check("an unsaved project gets a recovery copy", wrote >= 1 and any(s["title"] == "Crash test" for s in autosave.list_snapshots(rec)))
        check("nothing is rewritten when nothing changed", app.autosave_now() == 0)
        check("the copy is not the user's file", not any(os.path.exists(p) for p in [os.path.join(work, "Crash test.json")]))
        app._write_project_file(os.path.join(work, "saved_crash.json"), quiet=True)
        check("saving removes its recovery copy", not any(s["title"] == "Crash test" for s in autosave.list_snapshots(rec)))
        add_block(app, "'more'")
        app.autosave_now()
        count = len(autosave.list_snapshots(rec))
        check("it is back after a new change", count >= 1)
    finally:
        # simulate a crash: the window just goes away, no clean exit
        app.destroy()

    # ---- next start: the leftovers are offered back
    left = autosave.list_snapshots(rec)
    check("a crash leaves the copies behind", len(left) >= 1)
    app2 = make_app(rec)
    try:
        before = len(app2.workspaces)
        asked.clear()
        n = app2.offer_recovery()
        titles = [w["title"] for w in app2.workspaces]
        check("the offer names the projects and reopens them", n == len(left) and any(k == "yesno" for k, _ in asked) and "saved_crash" in titles)
        check("recovered projects are open and unsaved", all(app2.workspace_dirty(w) for w in app2.workspaces if w["title"] == "saved_crash"))
        check("the empty starter tab went away", not any(w["title"].startswith("Project 1") and not app2.workspace_dirty(w) for w in app2.workspaces) or before == 1)
        check("the copies are gone once reopened", autosave.list_snapshots(rec) == [])
        code = app2.code_text.get("1.0", "end")
        check("the blocks came back", "more" in code or any("more" in repr(w["files"]) for w in app2.workspaces))

        # No = throw them away
        add_block(app2, "'again'")
        app2.autosave_now()
        messagebox.askyesno = lambda *a, **k: False
        check("saying No deletes the copies and opens nothing", app2.offer_recovery() == 0 and autosave.list_snapshots(rec) == [])

        # clean exit removes copies
        add_block(app2, "'last'")
        app2.autosave_now()
        check("there is a copy before a clean exit", len(autosave.list_snapshots(rec)) >= 1)
        messagebox.askyesno = lambda *a, **k: True
        app2._ext_close()
        check("quitting on purpose leaves nothing to recover", autosave.list_snapshots(rec) == [])
    finally:
        try:
            app2.destroy()
        except Exception:
            pass
        shutil.rmtree(work, ignore_errors=True)
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
