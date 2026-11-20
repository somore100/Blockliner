"""Scripted UI test (run under Xvfb): File > Import GitHub Workflow opens a workflow as nodes in a new tab - one per job, the
`needs` of a job become wires, and a file that is not a workflow is refused with a message."""
import os, sys, tempfile, time
from tkinter import messagebox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

WF = """name: CI
on: [push]
jobs:
  build:
    steps:
      - run: echo build
  test:
    needs: build
    steps:
      - run: echo test
  deploy:
    needs: [build, test]
    steps:
      - run: echo deploy
"""

def settle(app, sec=0.2):
    end = time.time() + sec
    while time.time() < end:
        app.update_idletasks(); app.update(); time.sleep(0.01)

def main():
    shown = []
    messagebox.showinfo = lambda *a, **k: shown.append(("info", a))
    messagebox.showerror = lambda *a, **k: shown.append(("error", a))
    messagebox.askyesno = lambda *a, **k: False
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1300x800+0+0")
    try:
        settle(app)
        with tempfile.TemporaryDirectory() as d:
            good, bad = os.path.join(d, "ci.yml"), os.path.join(d, "notes.yml")
            open(good, "w").write(WF)
            open(bad, "w").write("hello: world\n")
            before = len(app.tabs)
            lines = app.import_github_workflow(good); settle(app, 0.3)
            check("a new tab was opened", len(app.tabs) == before + 1 and app.tabs[-1]["title"] == "ci")
            nodes = app.tabs[-1]["nodes"]
            by_name = {n["name"]: n for n in nodes}
            check("a node per job", {"job_build", "job_test", "job_deploy", "workflow", "main"} <= set(by_name))
            ids = {n["id"]: n["name"] for n in nodes}
            refs = {n["name"]: sorted(ids[r["id"]] if isinstance(r, dict) else ids[r] for r in n["references"]) for n in nodes}
            check(f"'needs' are wires ({refs.get('job_deploy')})", refs.get("job_deploy") == ["job_build", "job_test"] and refs.get("job_test") == ["job_build"])
            check("the user is told what happened", shown and shown[-1][0] == "info" and lines)
            shown.clear()
            tabs = len(app.tabs)
            check("a file that is not a workflow is refused", app.import_github_workflow(bad) is None and shown and shown[-1][0] == "error" and len(app.tabs) == tabs)
        check("the command is in the palette list", any(c[0] == "file.import_workflow" for c in __import__("ui_commands").CORE))
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
