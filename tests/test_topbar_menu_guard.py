"""Scripted UI test (run under Xvfb): a top-bar dropdown left open is closed by the popup guard
(the same one right-click menus use), so it can't stay on screen after minimizing."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(4):
        app.update_idletasks()
        app.update()


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+50+50")
    try:
        settle(app)
        menu = app.topbar_menus["Tools"]
        menu.post(200, 200)
        settle(app)
        check("the dropdown is on screen", menu.winfo_ismapped())
        check("the guard knows about it", app._active_popup is menu)
        app._dismiss_popup()
        settle(app)
        check("dismissing closes it", not menu.winfo_ismapped() and app._active_popup is None)
        menu.post(200, 200)
        settle(app)
        app.iconify()
        for _ in range(12):                       # the watcher polls every 250 ms
            app.after(100)
            app.update()
        check("minimizing closes it", not menu.winfo_ismapped())
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
