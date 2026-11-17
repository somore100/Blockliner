"""Follow a File: only that file is opened, other files in the folder are ignored, edits are written back to it."""
import os
import sys
import tempfile
import time
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []
messagebox.showinfo = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0")
    try:
        settle(app)
        with tempfile.TemporaryDirectory() as d:
            for name, body in (("a.py", "def one():\n    return 1\n"), ("b.py", "def two():\n    return 2\n")):
                with open(os.path.join(d, name), "w") as f:
                    f.write(body)
            app.settings["follow_sync_seconds"] = 0.1
            n = app.follow_file(os.path.join(d, "a.py"), write=True)
            settle(app)
            check("one file opened", n == 1 and sorted(app._follow["snap"]) == ["a.py"])
            check("b.py is not a followed tab", app._follow_tab("b.py") is None and app._follow_tab("a.py") is not None)
            with open(os.path.join(d, "b.py"), "a") as f:
                f.write("\n\ndef three():\n    return 3\n")
            app.follow_check_now()
            check("changes to other files are ignored", sorted(app._follow["snap"]) == ["a.py"])
            with open(os.path.join(d, "a.py"), "w") as f:
                f.write("def one():\n    return 11\n")
            added, changed, removed = app.follow_check_now()
            check("the followed file is still watched", changed == ["a.py"])
            check("presence lives in the file's folder", app._presence is None or app._presence["root"] == os.path.abspath(d))
            check("remembered as a file", app.settings.get("follow_only") == "a.py")
            app.stop_following(forget=True)
            check("forgotten", "follow_only" not in app.settings)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
