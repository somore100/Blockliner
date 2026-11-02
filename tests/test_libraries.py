"""Libraries, presets, search and tidy report (pure, no Tk)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import libraries as L

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "languages")
    py, notes = L.load_libraries(os.path.join(root, "python", "libraries"))
    check("python libraries load without notes", {"time", "math", "random", "tkinter"} <= set(py) and notes == [])
    check("each language has its own libraries", "fs" in L.load_libraries(os.path.join(root, "javascript", "libraries"))[0]
          and "stdlib.h" in L.load_libraries(os.path.join(root, "c", "libraries"))[0])
    check("a missing folder is no libraries", L.load_libraries("/nonexistent") == ({}, []))
    with tempfile.TemporaryDirectory() as d:
        json.dump({"name": "bad"}, open(os.path.join(d, "a.json"), "w"))
        open(os.path.join(d, "b.json"), "w").write("{nope")
        libs, n = L.load_libraries(d)
        check("damaged library files are skipped with notes", libs == {} and len(n) == 2)

    presets = L.load_presets(os.path.join(root, "python", "presets.json"), "/nonexistent")
    app = next(p for p in presets if p["name"] == "App basic")
    check("presets load", app["libraries"] == ["tkinter", "math", "time"])
    known, unknown = L.preset_libraries({"name": "x", "libraries": ["time", "ghost"]}, py)
    check("a preset naming an unknown library reports it", known == ["time"] and unknown == ["ghost"])
    check("import lines follow the ticks, once each", L.import_lines(py, ["tkinter", "math", "time", "math"])
          == ["import tkinter as tk", "import math", "import time"])

    hits = L.search_commands(py, "sleep")
    check("search finds a command and its library", hits and hits[0][0]["name"] == "time" and hits[0][1]["name"] == "sleep")
    check("search ranks exact before partial", L.search_commands(py, "random")[0][1]["name"] == "random"
          or L.search_commands(py, "random")[0][0]["name"] == "random")
    check("empty or unknown search is empty", L.search_commands(py, "") == [] and L.search_commands(py, "zzzqq") == [])

    check("a standard library is installed", L.installed(py["time"], "python") is True)
    ghost = dict(py["time"], installed_module="surely_not_a_real_module_xyz")
    check("a missing module is not installed", L.installed(ghost, "python") is False)
    check("other languages can't be checked", L.installed(py["time"], "javascript") is None)
    check("status colours", L.command_status(py["time"], ["time"], "python") == "imported"
          and L.command_status(py["time"], [], "python") == "available" and L.command_status(ghost, [], "python") == "not_installed")

    code = ["import time", "import time", "import math", "time.sleep(2)", "print(random.randint(1, 6))", "x = 1"]
    rep = L.tidy_report(py, code)
    check("missing: used but not imported", rep["missing"] == ["random"])
    check("unused: imported but never used (namespaced)", rep["unused"] == ["math"])
    check("duplicates are found", rep["duplicates"] == ["import time"])
    check("an alias counts as imported", L.imported_names(py, ["from time import *"]) == [] and
          L.imported_names({"t": {"name": "t", "import": "import time", "aliases": ["import time as t"], "namespace": "", "commands": []}}, ["import time as t"]) == ["t"])
    check("a similarly named variable is not a use", L.tidy_report(py, ["my_time.sleep(1)", "mytime = 2"])["missing"] == [])
    check("dedupe keeps the first import and everything else", L.dedupe_imports(py, code) == ["import time", "import math", "time.sleep(2)", "print(random.randint(1, 6))", "x = 1"])
    c, _n = L.load_libraries(os.path.join(root, "c", "libraries"))
    check("C functions count as use without a namespace", L.tidy_report(c, ["int *p = malloc(4);", "free(p);"])["missing"] == ["stdlib.h"])
    check("C unused is never guessed", L.tidy_report(c, ["#include <math.h>", "int x = 1;"])["unused"] == [])
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
