"""Scripted UI test (run under Xvfb): renaming a node while following a folder with write-back renames the function in
its file (Python and JavaScript) and, for Python, fixes the files that import it."""
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


def put(path, text):
    with open(path, "w", newline="") as f:
        f.write(text)


def get(path):
    with open(path, newline="") as f:
        return f.read()


def main():
    shown = []
    ui_follow.messagebox.showinfo = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    app.show_change_bar = lambda text, undo=True: shown.append(text)
    try:
        settle(app, 0.3)
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "pkg"))
            p_lib, p_main, p_from, p_js = (os.path.join(d, n) for n in ("pkg/lib.py", "main.py", "pkg/user.py", "app.js"))
            put(p_lib, "def util(x):\n    return x + 1\n\n\ndef other():\n    return util(2)\n")
            put(p_main, "import pkg.lib as lib\nfrom pkg.lib import util\n\nprint(lib.util(1), util(2), 'util')\n")
            put(p_from, "from .lib import util as u\nfrom . import lib\n\nu(1)\nlib.util(3)\n")
            put(p_js, "function old(a) {\n  return a + 1;\n}\n\nconsole.log(old(1), \"old\");\n")
            p_js2, p_go1, p_go2 = (os.path.join(d, n) for n in ("use.js", "a.go", "b.go"))
            put(p_js2, "import {old} from './app.js';\nold(2);\n")
            put(p_go1, "package m\n\nfunc Helper() int {\n\treturn 1\n}\n")
            put(p_go2, "package m\n\nfunc Run() int {\n\treturn Helper()\n}\n")
            app.follow_folder(d, write=True)
            settle(app, 0.4)
            tab = app._follow_tab("pkg/lib.py")
            check("the files are open and writable", tab is not None and tab["follow_state"]["writable"])
            node = [n for n in tab["nodes"] if n["name"] == "util"][0]
            ok, _m, _n = app.rename_node(tab, node, "helper")
            check("the rename is written", ok and app.follow_write_back(tab) is True)
            lib = get(p_lib)
            check("lib.py: definition and call renamed", "def helper(x)" in lib and "return helper(2)" in lib
                  and "util" not in lib)
            m = get(p_main)
            check("main.py: import, module attribute and bare use renamed, the string is not",
                  "from pkg.lib import helper" in m and "lib.helper(1)" in m and "helper(2)" in m and "'util'" in m)
            u = get(p_from)
            check("pkg/user.py: relative imports", "from .lib import helper as u" in u and "lib.helper(3)" in u)
            check("the user is told which files changed", any("main.py" in s and "user.py" in s for s in shown))

            # a clash in an importer is refused for that file only
            put(p_from, "from .lib import helper as u\nfrom . import lib\n\nu(1)\nlib.helper(3)\nbetter = 1\n")
            app.follow_check_now()
            tab = app._follow_tab("pkg/lib.py")
            node = [n for n in tab["nodes"] if n["name"] == "helper"][0]
            shown.clear()
            app.rename_node(tab, node, "better")
            app.follow_write_back(tab)
            check("a clash in an importer is reported and that file is left alone",
                  "lib.helper(3)" in get(p_from) and "better = 1" in get(p_from)
                  and any("Not changed" in s and "user.py" in s for s in shown))

            # JavaScript
            jt = app._follow_tab("app.js")
            check("the JS file is writable", jt is not None and jt["follow_state"]["writable"])
            app.switch_to_tab(app.tabs.index(jt))
            settle(app, 0.2)
            node = [n for n in jt["nodes"] if n["name"] == "old"][0]
            app.rename_node(jt, node, "fresh")
            check("a JS rename is written", app.follow_write_back(jt) is True)
            js = get(p_js)
            check("JS: definition and call renamed, the string is not", "function fresh(a)" in js
                  and "console.log(fresh(1)" in js and '"old"' in js)
            check("JS: the importing file is fixed too", get(p_js2) == "import {fresh} from './app.js';\nfresh(2);\n")

            gt = app._follow_tab("a.go")
            check("the Go file is writable", gt is not None and gt["follow_state"]["writable"])
            app.switch_to_tab(app.tabs.index(gt))
            settle(app, 0.2)
            node = [n for n in gt["nodes"] if n["name"] == "Helper"][0]
            app.rename_node(gt, node, "Assist")
            check("a Go rename is written", app.follow_write_back(gt) is True and "func Assist()" in get(p_go1))
            check("Go: the file of the same package is fixed too", "return Assist()" in get(p_go2))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
