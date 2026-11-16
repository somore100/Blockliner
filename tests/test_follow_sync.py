"""Scripted UI test (run under Xvfb): when edits to followed files are written - automatically after the pause set in
Settings, or only when File > Update Source Files is chosen."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_follow
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.0):
    end = time.time() + seconds
    while True:
        app.update_idletasks()
        app.update()
        if time.time() >= end:
            break
        time.sleep(0.01)


def raw(path):
    with open(path, "rb") as f:
        return f.read()


def edit(app, tab, name, code):
    node = [n for n in tab["nodes"] if n["name"] == name][0]
    blocks = app.import_code_to_blocks(code)[0]
    if app.tabs[app.active_tab_index] is tab and app.get_active_node(tab) is node:
        app.project_blocks[:] = blocks
    else:
        node["blocks"] = blocks


def main():
    shown = []
    ui_follow.messagebox.showinfo = lambda *a, **k: None
    asked = []
    ui_follow.messagebox.askyesno = lambda *a, **k: asked.append(a) or True
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0")
    app.show_change_bar = lambda text, undo=True: shown.append(text)
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.py")
            with open(p, "w") as f:
                f.write("def one():\n    return 1\n\n\ndef two():\n    return 2\n")
            app.follow_folder(d, write=True)
            settle(app, 0.3)
            tab = app._follow_tab("a.py")
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)

            check("the default pause is 0.6 s", app.follow_delay_ms() == 600)
            app.settings["follow_sync_seconds"] = 1.5
            check("the pause comes from Settings", app.follow_delay_ms() == 1500)
            edit(app, tab, "one", "def one():\n    return 11\n")
            app.mark_active_tab_dirty()
            settle(app, 0.9)
            check("not written before the pause is over", b"return 11" not in raw(p))
            settle(app, 1.2)
            check("written after it", b"return 11" in raw(p))

            app.settings["follow_sync_mode"] = "manual"
            edit(app, tab, "two", "def two():\n    return 22\n")
            app.mark_active_tab_dirty()
            settle(app, 2.2)
            check("manual: nothing is written by itself", b"return 22" not in raw(p))
            check("manual: the user is told how to write", any("Update Source Files" in s for s in shown))
            check("manual: the waiting file is known", tab in app.follow_waiting_tabs())
            check("Update Source Files writes it", app.follow_update_now() == 1 and b"return 22" in raw(p))
            check("and then nothing is waiting", app.follow_waiting_tabs() == [] and app.follow_update_now() == 0)

            edit(app, tab, "one", "def one():\n    return 111\n")
            app.mark_active_tab_dirty()
            app.stop_following()
            check("stopping asks about waiting edits in manual mode and writes them on yes",
                  asked and b"return 111" in raw(p))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
