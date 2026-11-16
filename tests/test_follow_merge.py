"""Scripted UI test (run under Xvfb): the "Merge" answer of the file-changed-on-disk dialog - clean merges, conflicts
resolved on the spot or written as markers, Resolve Conflicts, and cancelling."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import source_merge
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


def put(path, text):
    with open(path, "w", newline="") as f:
        f.write(text)


def get(path):
    with open(path, newline="") as f:
        return f.read()


def edit(app, tab, name, code):
    node = [n for n in tab["nodes"] if n["name"] == name][0]
    blocks = app.import_code_to_blocks(code)[0]
    if app.tabs[app.active_tab_index] is tab and app.get_active_node(tab) is node:
        app.project_blocks[:] = blocks
    else:
        node["blocks"] = blocks


SRC = "def one():\n    return 1\n\n\ndef two():\n    return 2\n\n\ndef three():\n    return 3\n"


def main():
    shown = []
    ui_follow.messagebox.showinfo = lambda *a, **k: None
    ui_follow.messagebox.askyesno = lambda *a, **k: True
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0")
    app.show_change_bar = lambda text, undo=True: shown.append(text)
    answers = []
    app.ask_follow_conflict = lambda rel: answers.pop(0) if answers else "theirs"
    resolves = []
    real_resolve = app.ask_follow_resolve
    app.ask_follow_resolve = lambda rel, regions, allow_markers=False: resolves.pop(0) if resolves else None
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.py")
            put(p, SRC)
            app.follow_folder(d, write=True)
            settle(app, 0.3)
            tab = app._follow_tab("m.py")
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)

            # 1. a clean merge: I change one, they changed two
            edit(app, tab, "one", "def one():\n    return 11\n")
            put(p, SRC.replace("return 2", "return 22"))
            answers[:] = ["merge"]
            check("a clean merge is written", app.follow_write_back(tab) is True)
            text = get(p)
            check("both changes are in the file, nothing marked", "return 11" in text and "return 22" in text
                  and not source_merge.has_conflicts(text))
            tab = app._follow_tab("m.py")
            check("the file is writable again and the tab shows the merge", tab["follow_state"]["writable"]
                  and app.follow_waiting_tabs() == [])

            # 2. a conflict resolved on the spot (both: theirs, then mine)
            edit(app, tab, "three", "def three():\n    return 33\n")
            put(p, get(p).replace("return 3\n", "return 300\n"))
            answers[:] = ["merge"]
            resolves[:] = [["both"]]
            check("a conflict can be resolved while merging", app.follow_write_back(tab) is True)
            text = get(p)
            check("both versions are in the file, no markers", "return 300" in text and "return 33" in text
                  and not source_merge.has_conflicts(text) and text.index("return 300") < text.index("return 33"))

            # 3. conflict markers
            tab = app._follow_tab("m.py")
            edit(app, tab, "one", "def one():\n    return 111\n")
            put(p, get(p).replace("return 11\n", "return 1000\n"))
            answers[:] = ["merge"]
            resolves[:] = ["markers"]
            app.follow_write_back(tab)
            text = get(p)
            tab = app._follow_tab("m.py")
            check("markers are written for the conflicting node only", source_merge.count_conflicts(text) == 1
                  and "return 111" in text and "return 1000" in text and "def two()" in text)
            check("the file is read-only here until resolved", not tab["follow_state"]["writable"]
                  and "conflict" in tab["follow_state"]["why"])
            shown.clear()
            app.mark_active_tab_dirty()
            settle(app, 0.2)

            # 4. Resolve Conflicts
            resolves[:] = [["mine"]]
            check("Resolve Conflicts resolves the file", app.follow_resolve_conflicts() == 1)
            text = get(p)
            tab = app._follow_tab("m.py")
            check("with my side, no markers, writable again", "return 111" in text and "return 1000" not in text
                  and not source_merge.has_conflicts(text) and tab["follow_state"]["writable"])

            # 5. cancelling leaves the file and the edit alone
            edit(app, tab, "two", "def two():\n    return 222\n")
            put(p, get(p).replace("return 22\n", "return 2000\n"))
            before = get(p)
            answers[:] = ["merge"]
            resolves[:] = [None]
            check("cancelling writes nothing", app.follow_write_back(tab) is False and get(p) == before)
            check("and the edit is still waiting", tab in app.follow_waiting_tabs() or
                  [n for n in app._follow_tab("m.py")["nodes"] if n["name"] == "two"] != [])

            # the real resolve window
            def press():
                top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][-1]
                for fr in top.winfo_children():
                    for b in fr.winfo_children():
                        if b.winfo_class() == "Button" and b.cget("text") == "Apply choices":
                            b.invoke()
                            return
            app.after(200, press)
            got = real_resolve("m.py", [("mine\n", "theirs\n"), ("m2\n", "t2\n")])
            check("the real window returns the choices (both by default)", got == ["both", "both"])
            app.after(200, lambda: [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][-1].destroy())
            check("closing it cancels", real_resolve("m.py", [("a\n", "b\n")]) is None)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
