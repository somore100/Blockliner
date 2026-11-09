"""Scripted UI test (run under Xvfb): top-bar dropdowns and the Run arrow open and STAY open when
clicked, and a menu left open is closed by the popup guard (so it can't stay on screen after minimizing)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def click(app, w):
    """A real press and release at the widget's centre (mouse events are routed by screen position)."""
    x, y = w.winfo_width() // 2, w.winfo_height() // 2
    rx, ry = w.winfo_rootx() + x, w.winfo_rooty() + y
    w.event_generate("<Motion>", x=x, y=y, rootx=rx, rooty=ry)
    w.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx, rooty=ry)
    settle(app, 0.1)
    w.event_generate("<ButtonRelease-1>", x=x, y=y, rootx=rx, rooty=ry)
    settle(app, 0.3)


def menubuttons(w):
    out = []
    for c in w.winfo_children():
        if c.winfo_class() == "Menubutton":
            out.append(c)
        out += menubuttons(c)
    return out


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+50+50")
    try:
        settle(app, 0.8)
        by_text = {m.cget("text"): m for m in menubuttons(app)}

        # clicking a menu button opens its menu and it stays open (it used to flash and vanish)
        for title in ("File", "Tools", "Help"):
            click(app, by_text[title])
            menu = app.topbar_menus[title]
            check(f"clicking {title} opens its menu and it stays open", menu.winfo_ismapped())
            menu.unpost()
            app.tk.call("tk::MenuUnpost", str(menu))
            settle(app)

        # a posted menu is closed by the guard
        menu = app.topbar_menus["Tools"]
        menu.post(200, 200)
        settle(app)
        check("a posted dropdown is on screen", menu.winfo_ismapped())
        check("the guard knows about it", app._active_popup is menu)
        app._dismiss_popup()
        settle(app)
        check("dismissing closes it", not menu.winfo_ismapped() and app._active_popup is None)

        menu.post(200, 200)
        settle(app)
        app.state = lambda *a: "iconic"             # Xvfb has no window manager to minimize for real
        for _ in range(12):                         # the watcher polls every 250 ms
            settle(app, 0.1)
        check("minimizing closes it", not menu.winfo_ismapped())
        del app.state

        # the Run arrow
        arrow = next(w for w in app.run_button.master.winfo_children() if w.winfo_class() == "Label")
        click(app, arrow)
        check("clicking the Run arrow opens its menu and it stays open",
              app._active_popup is not None and app._active_popup.winfo_ismapped())
        app._dismiss_popup()
        settle(app)

        # a click elsewhere still closes a menu
        menu = app.topbar_menus["File"]
        menu.post(200, 200)
        settle(app, 0.6)
        app._on_any_press(type("E", (), {"widget": app.workspace_canvas})())
        settle(app)
        check("clicking elsewhere closes it", not menu.winfo_ismapped())
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
