"""Scripted UI test (run under Xvfb): closing the window asks first when a project has unsaved changes."""
import os
import sys
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def alive(app):
    try:
        return bool(app.winfo_exists())
    except Exception:
        return False


def main():
    asked = []
    answer = {"v": False}
    messagebox.askyesno = lambda *a, **k: (asked.append(a), answer["v"])[1]
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        app.update()
        check("a fresh blank project counts as nothing to save", app.unsaved_workspace_titles() == [])
        app.goto_layer("blocks")
        app.project_blocks.append(("comment", {"text": "x"}))
        app.mark_active_tab_dirty()
        check("a project with blocks and changes is listed", len(app.unsaved_workspace_titles()) == 1)
        app._ext_close()
        check("answering No keeps the window open", alive(app) and len(asked) == 1)
        answer["v"] = True
        app._ext_close()
        check("answering Yes closes it", not alive(app) and len(asked) == 2)
    finally:
        if alive(app):
            app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
