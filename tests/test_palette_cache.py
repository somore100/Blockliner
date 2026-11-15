"""Scripted UI test (run under Xvfb): opening a file / switching layers keeps the palette widgets when nothing the
palette shows changed (rebuilding ~450 widgets each time made opening a file slow on a real desktop); a search,
a language switch or a colour change still rebuilds it."""
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


def settle(app, seconds=0.0):
    end = time.time() + seconds
    while True:
        app.update_idletasks()
        app.update()
        if time.time() >= end:
            break
        time.sleep(0.01)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        settle(app, 0.6)                                   # the palette builds a few rows per idle step
        first = set(map(str, app.palette_frame.winfo_children()))
        check("the palette is built", len(first) > 50)
        app.open_file_from_files_view(0)
        settle(app, 0.3)
        app.goto_layer("files")
        app.open_file_from_files_view(0)
        settle(app, 0.3)
        check("opening a file again keeps the same palette widgets", set(map(str, app.palette_frame.winfo_children())) == first)
        app.refresh_palette()
        check("refresh_palette with nothing changed keeps them too", set(map(str, app.palette_frame.winfo_children())) == first)

        app.search_var.set("print")
        app.refresh_palette()
        settle(app, 0.3)
        check("a search rebuilds the palette", set(map(str, app.palette_frame.winfo_children())) != first)
        app.search_var.set("")
        app.refresh_palette()
        settle(app, 0.6)
        check("clearing the search brings the full palette back", len(app.palette_frame.winfo_children()) >= len(first))

        before = set(map(str, app.palette_frame.winfo_children()))
        from ui_common import CATEGORY_COLORS
        old = CATEGORY_COLORS["Math"]
        CATEGORY_COLORS["Math"] = "#123456"
        app.refresh_palette()
        settle(app, 0.6)
        check("a changed category colour rebuilds it", set(map(str, app.palette_frame.winfo_children())) != before)
        CATEGORY_COLORS["Math"] = old
        app.refresh_palette()
        settle(app, 0.6)

        app.lang_var.set("javascript")
        app.current_language = "javascript"
        app.load_blocks_for_language("javascript")
        app.refresh_palette()
        settle(app, 0.6)
        check("another language rebuilds it with that language's blocks", app._palette_sig[0] == "javascript")
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
