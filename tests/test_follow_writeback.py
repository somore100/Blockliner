"""Scripted UI test (run under Xvfb): source-first phase 2. Following a folder with write-back on puts an edit made to a
block back into its file - only the edited node, everything else byte for byte - and never overwrites a file that
another program changed first."""
import hashlib
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


def put(path, data):
    with open(path, "wb") as f:
        f.write(data)


def raw(path):
    with open(path, "rb") as f:
        return f.read()


def edit_node(app, tab, name, code):
    """Replace the blocks of one node with the blocks of `code`, the way an edit on screen would."""
    node = [n for n in tab["nodes"] if n["name"] == name][0]
    blocks = app.import_code_to_blocks(code)[0]
    if app.tabs[app.active_tab_index] is tab and app.get_active_node(tab) is node:
        app.project_blocks[:] = blocks
    else:
        node["blocks"] = blocks
    return node


APP = (b"import os\n\n\ndef greet(name):\n  print( name )   # odd spacing on purpose\n\n\n"
       b"def shout(name):\n    print(name.upper())\n\ngreet('x')\n")


def main():
    shown = []
    ui_follow.messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    app.show_change_bar = lambda text, undo=True: shown.append(text)
    answers = []
    real_ask = app.ask_follow_conflict
    app.ask_follow_conflict = lambda rel: answers.pop(0) if answers else "theirs"
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            p_app, p_win, p_latin = (os.path.join(d, n) for n in ("app.py", "win.py", "latin.py"))
            put(p_app, APP)
            put(p_win, b"def one():\r\n    return 1\r\n\r\ndef two():\r\n    return 2\r\n")
            put(p_latin, "def caf\xe9():\n    return 1\n".encode("latin-1"))
            app.follow_folder(d, write=True)
            settle(app, 0.3)
            tab = app._follow_tab("app.py")
            check("write-back is on and the files are armed", app._follow["write"] and tab["follow_state"]["writable"]
                  and app._follow_tab("win.py")["follow_state"]["writable"])
            check("a file that is not UTF-8 is not writable (and says why)",
                  not app._follow_tab("latin.py")["follow_state"]["writable"]
                  and "UTF-8" in app._follow_tab("latin.py")["follow_state"]["why"])

            # nothing edited: not touched
            st = os.stat(p_app)
            check("no edit -> nothing written", app.follow_write_back(tab) is False and raw(p_app) == APP
                  and os.stat(p_app).st_mtime_ns == st.st_mtime_ns)

            # one node edited (the tab is not the one on screen)
            app.switch_to_tab(app.tabs.index(app._follow_tab("win.py")))
            settle(app, 0.2)
            edit_node(app, tab, "shout", "def shout(name):\n    print(name.lower())\n")
            check("an edit is written back", app.follow_write_back(tab) is True)
            now = raw(p_app)
            check("only that node changed", b"lower" in now and b"upper" not in now
                  and b"  print( name )   # odd spacing on purpose\n" in now and now.startswith(APP[:APP.index(b"def shout")])
                  and now.endswith(b"\ngreet('x')\n"))
            check("our own write is not taken for an outside change", app.follow_check_now() == ([], [], []))
            check("the tab is not 'unsaved' and the user is told", tab["dirty"] is False and any("Saved" in s for s in shown))
            check("the same blocks again -> nothing more to write", app.follow_write_back(tab) is False)

            # a CRLF file keeps its line ends
            wt = app._follow_tab("win.py")
            edit_node(app, wt, "two", "def two():\r\n    return 22\r\n".replace("\r\n", "\n"))
            app.follow_write_back(wt)
            data = raw(p_win)
            check("Windows line ends are kept", b"return 22\r\n" in data and b"\r\n" in data
                  and data.replace(b"\r\n", b"").count(b"\n") == 0)

            # the debounced path: the edit on the tab that is on screen is written a moment later
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)
            edit_node(app, tab, "greet", "def greet(name):\n    print('hi', name)\n")
            app.mark_active_tab_dirty()
            check("writing waits a moment (typing makes many edits)", b"'hi'" not in raw(p_app))
            settle(app, ui_follow.WRITE_DELAY_MS / 1000 + 0.5)
            check("and then the edit is in the file", b"'hi'" in raw(p_app) and b"lower" in raw(p_app))

            # the file changed on disk first: it is never overwritten
            edit_node(app, tab, "shout", "def shout(name):\n    print('mine')\n")
            theirs = raw(p_app) + b"\ndef extra():\n    return 7\n"
            put(p_app, theirs)
            before = hashlib.sha1(theirs).hexdigest()
            shown.clear()
            answers[:] = ["theirs"]
            wrote = app.follow_write_back(tab)
            tab = app._follow_tab("app.py")
            check("an outside change wins over a pending edit", wrote is False
                  and hashlib.sha1(raw(p_app)).hexdigest() == before and b"mine" not in raw(p_app))
            check("and the user is told", any("changed on disk first" in s for s in shown))
            check("the tab shows their version", "extra" in [n["name"] for n in tab["nodes"]])

            # the real dialog: each button answers, closing the window means theirs
            def press(index):
                def go():
                    top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][-1]
                    btns = [b for fr in top.winfo_children() for b in fr.winfo_children()]
                    if index is None:
                        top.event_generate("<Destroy>")
                        top.destroy()
                    else:
                        btns[index].invoke()
                app.after(150, go)
            got = []
            for i in (0, 1, 2):
                press(i)
                got.append(real_ask("app.py"))
            check("the dialog's three buttons answer mine / theirs / copy", got == ["mine", "theirs", "copy"])

            # phase 3: keep mine overwrites the file with my version
            edit_node(app, tab, "shout", "def shout(name):\n    print('mine')\n")
            put(p_app, raw(p_app) + b"\n# outside\n")
            answers[:] = ["mine"]
            check("keep mine writes my edit over their change", app.follow_write_back(tab) is True
                  and b"'mine'" in raw(p_app) and b"# outside" not in raw(p_app))
            check("and that write is not taken for an outside change", app.follow_check_now() == ([], [], []))

            # save as a copy: my version goes to the chosen file, theirs is shown
            edit_node(app, tab, "shout", "def shout(name):\n    print('copy me')\n")
            put(p_app, raw(p_app) + b"\n# outside 2\n")
            mine_copy = os.path.join(d, "mine.txt")
            ui_follow.filedialog.asksaveasfilename = lambda **k: mine_copy
            answers[:] = ["copy"]
            check("save as copy does not write the file", app.follow_write_back(tab) is False
                  and b"copy me" not in raw(p_app) and b"# outside 2" in raw(p_app))
            check("the copy holds my version", os.path.exists(mine_copy) and b"copy me" in raw(mine_copy))
            tab = app._follow_tab("app.py")

            # an outside change while an edit still waits for its write: asked by the watcher too
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)
            edit_node(app, tab, "shout", "def shout(name):\n    print('pending')\n")
            app.mark_active_tab_dirty()
            put(p_app, raw(p_app) + b"\n# outside 3\n")
            answers[:] = ["mine"]
            app.follow_check_now()
            check("the watcher asks and keep mine wins", b"'pending'" in raw(p_app) and not answers)
            tab = app._follow_tab("app.py")
            edit_node(app, tab, "shout", "def shout(name):\n    print('pending 2')\n")
            app.mark_active_tab_dirty()
            put(p_app, raw(p_app) + b"\n# outside 4\n")
            answers[:] = ["theirs"]
            app.follow_check_now()
            settle(app, ui_follow.WRITE_DELAY_MS / 1000 + 0.3)
            check("the watcher asks and take theirs drops the edit", b"pending 2" not in raw(p_app)
                  and b"# outside 4" in raw(p_app) and not answers)

            # execution order changed here -> the nodes change places in the file
            tab = app._follow_tab("app.py")
            names = [n["name"] for n in tab["nodes"]]
            first, last = [n for n in tab["nodes"] if n["name"] == names[0]][0], [n for n in tab["nodes"] if n["name"] == names[-1]][0]
            ok, _m, _h = app.set_node_order(tab, last, 1, on_conflict="swap")
            before = raw(p_app)
            want = app._follow_order(tab)
            check("a changed execution order is written", ok and app.follow_write_back(tab) is True
                  and raw(p_app) != before)
            check("the file's nodes come back in that order", [i for i, _c in tab["follow_state"]["chunks"]] == want)
            app.follow_check_now()
            tab = app._follow_tab("app.py")

            # a node deleted here is dropped from the file
            app.follow_check_now()
            tab = app._follow_tab("app.py")
            tab["nodes"] = [n for n in tab["nodes"] if n["name"] != "extra"]
            check("deleting a node writes", app.follow_write_back(tab) is True and b"extra" not in raw(p_app)
                  and b"def greet" in raw(p_app))

            # not writable: stays on screen only
            lt = app._follow_tab("latin.py")
            lat = raw(p_latin)
            app.switch_to_tab(app.tabs.index(lt))
            settle(app, 0.2)
            shown.clear()
            app.mark_active_tab_dirty()
            settle(app, ui_follow.WRITE_DELAY_MS / 1000 + 0.3)
            check("a file that cannot be written exactly is left alone, with a notice",
                  raw(p_latin) == lat and any("read-only here" in s for s in shown))

            # stopping flushes an edit that is still waiting
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)
            edit_node(app, tab, "greet", "def greet(name):\n    print('bye', name)\n")
            app.mark_active_tab_dirty()
            app.stop_following()
            check("stop following writes the edit still waiting", b"'bye'" in raw(p_app))
            check("and the marks are gone", not any("followed" in t or "follow_state" in t for t in app.tabs))

            # read-only follow: nothing is ever written
            app.follow_folder(d, write=False)
            settle(app, 0.3)
            ro = app._follow_tab("app.py")
            snapshot = raw(p_app)
            edit_node(app, ro, "greet", "def greet(name):\n    print('nope')\n")
            check("read-only: no write-back", app.follow_write_back(ro) is False and raw(p_app) == snapshot)
            app.stop_following()

            # the choice is remembered with the folder
            app.follow_folder(d, write=True)
            check("the write choice is remembered", app.settings.get("follow_write") is True)
            app.stop_following(forget=True)
            check("and forgotten with it", "follow_write" not in app.settings)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
