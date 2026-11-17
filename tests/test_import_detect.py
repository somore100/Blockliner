"""Scripted UI test (run under Xvfb): pasting code of another language offers to switch to it."""
import os, sys, time
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_import
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

GO = "package main\n\nimport \"fmt\"\n\nfunc main() {\n    x := 3\n    fmt.Println(x)\n}\n"
PY = "import os\n\ndef greet(name):\n    print(name)\n    return None\n"

def main():
    asked = []
    answer = {"v": True}
    def yes(title, msg, **k):
        asked.append(title)
        return answer["v"] if title == "Switch Language?" else True
    for m in (messagebox, ui_import.messagebox):
        m.askyesno = yes
        m.showinfo = lambda *a, **k: None
        m.showwarning = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        for _ in range(5): app.update()
        check("starts in python", app.current_language == "python")
        app._convert_code_string_to_blocks(PY)
        check("python code in python: no question", "Switch Language?" not in asked and app.current_language == "python")
        answer["v"] = False
        app._convert_code_string_to_blocks(GO)
        check("go code in python: asked, declined, stays", "Switch Language?" in asked and app.current_language == "python")
        asked.clear(); answer["v"] = True
        app._convert_code_string_to_blocks(GO)
        check("go code in python: accepted, switches to go", app.current_language == "go")
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)
main()
