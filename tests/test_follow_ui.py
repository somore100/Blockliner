"""Scripted UI test (run under Xvfb): Follow a folder opens its source files as file tabs with nodes from their
structure, and when another program changes, adds or deletes a file the layers follow - nodes keep their places,
the user's current tab stays current, and nothing is written into the folder."""
import os
import sys
import tempfile
import time
from tkinter import messagebox

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


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def tree_state(d):
    out = {}
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[n] = f.read()
    return out


def main():
    ui_follow.messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "app.py"), "import os\n\ndef greet(name):\n    print(name)\n\ndef shout(name):\n    print(name.upper())\n\ngreet('x')\n")
            write(os.path.join(d, "util.py"), "def add(a, b):\n    return a + b\n")
            write(os.path.join(d, "readme.txt"), "ignored")
            before = tree_state(d)
            n0 = len(app.tabs)
            opened = app.follow_folder(d, write=False)
            settle(app, 0.3)
            check("two source files opened as tabs", opened == 2 and len(app.tabs) == n0 + 2)
            tab = app._follow_tab("app.py")
            names = [n["name"] for n in tab["nodes"]]
            check("nodes come from the file's structure", "greet" in names and "shout" in names and len(names) >= 3)
            check("followed tabs are not 'unsaved'", not tab["dirty"] and not app._follow_tab("util.py")["dirty"])

            # the user is looking at util.py; another tool changes app.py
            app.switch_to_tab(app.tabs.index(app._follow_tab("util.py")))
            settle(app, 0.2)
            greet = [n for n in tab["nodes"] if n["name"] == "greet"][0]
            greet["canvas_x"], greet["canvas_y"] = 777, 333
            write(os.path.join(d, "app.py"), "import os\n\ndef greet(name):\n    print('hello', name)\n\ndef shout(name):\n    print(name.upper())\n\ndef whisper(name):\n    print(name.lower())\n\ngreet('x')\n")
            added, changed, removed = app.follow_check_now()
            settle(app, 0.2)
            check("the change is noticed", changed == ["app.py"] and not added and not removed)
            tab = app._follow_tab("app.py")
            names = [n["name"] for n in tab["nodes"]]
            check("a new function became a node", "whisper" in names)
            greet = [n for n in tab["nodes"] if n["name"] == "greet"][0]
            check("existing nodes keep their position", (greet["canvas_x"], greet["canvas_y"]) == (777, 333))
            code = app.generate_code_for_tab(tab, "python")
            check("the new text is what the blocks generate", "hello" in code and "whisper" in code)
            check("the tab the user was in stays current", app.tabs[app.active_tab_index] is app._follow_tab("util.py"))

            write(os.path.join(d, "extra.py"), "VALUE = 3\n")
            os.remove(os.path.join(d, "util.py"))
            added, changed, removed = app.follow_check_now()
            settle(app, 0.2)
            check("a new file appears and a deleted one is marked missing",
                  added == ["extra.py"] and removed == ["util.py"] and app._follow_tab("extra.py") is not None
                  and app._follow_tab("util.py")["title"].endswith("(missing)"))
            check("the missing file's tab is kept (nothing is closed under the user)", app._follow_tab("util.py") in app.tabs)

            check("quiet folder: nothing happens", app.follow_check_now() == ([], [], []))
            check("the timer is running", app._follow is not None and app._follow["job"] is not None)


            # a renamed function keeps its node's place
            tab = app._follow_tab("app.py")
            shout = [n for n in tab["nodes"] if n["name"] == "shout"][0]
            shout["canvas_x"], shout["canvas_y"] = 555, 222
            write(os.path.join(d, "app.py"), open(os.path.join(d, "app.py"), encoding="utf-8").read().replace("shout", "yell"))
            app.follow_check_now()
            settle(app, 0.2)
            tab = app._follow_tab("app.py")
            yell = [n for n in tab["nodes"] if n["name"] == "yell"]
            check("a renamed function keeps its place", len(yell) == 1 and (yell[0]["canvas_x"], yell[0]["canvas_y"]) == (555, 222))

            # editing a followed tab here is only on screen: it stays clean and the user is told
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)
            shown = []
            app.show_change_bar = lambda text, undo=True: shown.append(text)
            app.mark_active_tab_dirty()
            app.mark_active_tab_dirty()
            check("an edit on a followed tab does not make it unsaved", tab["dirty"] is False)
            check("the user is told once (not on every edit)", len(shown) == 1 and "not saved" in shown[0])
            tab["follow_notice_at"] -= ui_follow.NOTICE_SECONDS + 1
            app.mark_active_tab_dirty()
            check("and again after a while", len(shown) == 2)
            plain = [t for t in app.tabs if "followed" not in t][0]
            app.switch_to_tab(app.tabs.index(plain))
            app.mark_active_tab_dirty()
            check("a normal tab is still marked unsaved", plain["dirty"] is True and len(shown) == 2)

            # remembered between runs
            check("the folder is remembered", app.settings.get("follow_folder") == os.path.abspath(d))
            app.stop_following()
            asked = []
            messagebox.askyesno = lambda *a, **k: (asked.append(a), True)[1]
            check("offered again at startup and re-followed", app.offer_follow_again() is True and app._follow is not None
                  and len(asked) == 1 and d in asked[0][1])
            messagebox.askyesno = lambda *a, **k: False
            app.stop_following()
            check("saying no forgets it", app.offer_follow_again() is False and "follow_folder" not in app.settings)
            app.settings["follow_folder"] = os.path.join(d, "gone")
            check("a folder that no longer exists is dropped quietly", app.offer_follow_again() is False
                  and "follow_folder" not in app.settings)
            app.follow_folder(d, write=False)
            app.stop_following(forget=True)
            check("Stop Following forgets the folder", "follow_folder" not in app.settings)

            after = tree_state(d)
            after_expected = dict(before)
            check("Blockliner never wrote into the folder",
                  all(after.get(k) == v for k, v in after_expected.items() if k not in ("app.py", "util.py"))
                  and set(after) == {"app.py", "readme.txt", "extra.py"}
                  and b"hello" in after["app.py"])
            app.stop_following()
            check("stop following ends the timer and the marks", app._follow is None and not any("followed" in t for t in app.tabs))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
