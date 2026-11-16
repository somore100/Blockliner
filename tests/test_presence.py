"""Presence: the pure file format (who is where, stale files, git exclude) and the UI (two apps in one folder: tags on
node boxes, an own file written and removed, a warning when both edit one node)."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import presence as P

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def pure():
    with tempfile.TemporaryDirectory() as d:
        now = time.time()
        a = P.build("ann-1", "Ann", "#e5484d", {"a.py": {"open": ["one"], "editing": {"two": {"line": 12}}}}, now)
        b = P.build("ben-2", "Ben", "#3ecf8e", {"a.py": {"open": ["one"], "editing": {}}}, now)
        old = P.build("old-3", "Old", "#888888", {"a.py": {"open": ["one"], "editing": {}}}, now - 100)
        for doc in (a, b, old):
            P.write(d, doc)
        others = P.read_others(d, "ann-1", now)
        check("others are read, own file and stale files are not", [o["user"] for o in others] == ["Ben"])
        P.write(d, P.build("dead-4", "Dead", "#888888", {}, now - 1000))
        P.read_others(d, "ann-1", now)
        check("a long-dead file is deleted", not os.path.exists(P.path_of(d, "dead-4")))
        both = P.by_node(P.read_others(d, "ben-2", now), now)
        check("by_node lists open and editing", [p["user"] for p in both[("a.py", "one")]] == ["Ann"]
              and both[("a.py", "two")][0]["editing"] and both[("a.py", "two")][0]["line"] == 12)
        check("the tag says who and where", P.tag(both[("a.py", "two")]) == "✎ Ann · line 12"
              and P.tag(both[("a.py", "one")]) == "● Ann")
        P.remove(d, "ann-1")
        check("remove deletes a file", not os.path.exists(P.path_of(d, "ann-1")))
        with open(P.path_of(d, "bad-5"), "w") as f:
            f.write("{not json")
        check("a broken file is skipped", [o["user"] for o in P.read_others(d, "x", now)] == ["Ben"])
        check("names are made safe for file names", P.clean_name("../a b") == "ab" or P.clean_name("../a b") == "a_b"
              or "/" not in P.clean_name("../a b"))
        check("a colour is chosen per name, always the same", P.color_for("Ann") == P.color_for("Ann")
              and P.color_for("Ann") in P.PALETTE)
    with tempfile.TemporaryDirectory() as d:
        check("no .git: nothing to exclude", P.ensure_git_excluded(d) is False)
        os.makedirs(os.path.join(d, ".git"))
        check("added to .git/info/exclude", P.ensure_git_excluded(d) is True
              and ".blockliner/" in open(os.path.join(d, ".git", "info", "exclude")).read())
        check("and only once", P.ensure_git_excluded(d) is False)


def ui():
    import ui_follow
    from ui import BlocklinerUI
    ui_follow.messagebox.showinfo = lambda *a, **k: None

    def settle(app, seconds=0.0):
        end = time.time() + seconds
        while True:
            app.update_idletasks()
            app.update()
            if time.time() >= end:
                break
            time.sleep(0.01)

    shown = []
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0")
    app.show_change_bar = lambda text, undo=True: shown.append(text)
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.py"), "w") as f:
                f.write("def one():\n    return 1\n\n\ndef two():\n    return 2\n")
            app.settings["presence_on"] = False
            app.follow_folder(d, write=True)
            settle(app, 0.3)
            check("off by default: no presence folder", not os.path.exists(P.folder_of(d)) and app._presence is None)
            app.stop_following()

            app.settings["presence_on"] = True
            app.settings["presence_name"] = "Me"
            app.follow_folder(d, write=True)
            settle(app, 0.3)
            me = app._presence["id"]
            check("on: our own file is written", os.path.exists(P.path_of(d, me)))
            tab = app._follow_tab("a.py")
            app.switch_to_tab(app.tabs.index(tab))
            settle(app, 0.2)
            app.goto_layer("nodes")
            settle(app, 0.3)
            nid = tab["nodes"][0]["id"]
            P.write(d, P.build("ann-9", "Ann", "#e5484d",
                               {"a.py": {"open": [nid], "editing": {nid: {"line": 1}}}}))
            app.presence_tick()
            settle(app, 0.4)
            check("the other person is known", ("a.py", nid) in app._presence["others"])
            labels = []

            def walk(w):
                for c in w.winfo_children():
                    if c.winfo_class() == "Label":
                        labels.append(c.cget("text"))
                    walk(c)
            walk(app.workspace_canvas)
            check("their tag is on the node box", any("Ann" in t and "line 1" in t for t in labels))

            tab["active_node_id"] = nid
            app.presence_note_edit(tab)
            check("editing the same node warns", any("Ann is editing this node" in s for s in shown))
            app.presence_tick()
            mine = json.load(open(P.path_of(d, me)))
            check("our file says we are editing it", nid in mine["files"]["a.py"]["editing"]
                  and mine["files"]["a.py"]["editing"][nid]["line"] == 1)
            app.stop_following()
            check("stopping removes our file", not os.path.exists(P.path_of(d, me)))
    finally:
        app.destroy()


pure()
ui()
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
