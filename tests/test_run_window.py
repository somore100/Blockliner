"""Scripted UI test (run under Xvfb): Run opens a window, output streams in, input() is answered from the box,
Stop ends a loop, errors show, Run again works, closing the window ends the program."""
import os
import sys
import time
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes_model import make_node
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


def wait(app, cond, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        settle(app)
        if cond():
            return True
        time.sleep(0.05)
    return False


def main():
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showwarning = lambda *a, **k: None
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    app.settings["python_command"] = os.environ.get("BLOCKLINER_TEST_PYTHON") or sys.executable
    try:
        settle(app)
        tab = app.tabs[app.active_tab_index]
        node = app.get_active_node(tab)
        node["blocks"][:] = [("print_output", {"value": "'hello from a program'"})]
        app.refresh_workspace()
        app.update_generated_code()
        settle(app)

        view = app.run_code()
        check("Run opens a window", view is not None and view.win.winfo_exists())
        check("the program's output appears and the run is marked finished",
              wait(app, lambda: view.status_text == "Finished") and "hello from a program" in view.contents())
        check("Stop is greyed out and Run again is on once it is over", str(view.stop_btn["state"]) == "disabled" and str(view.again_btn["state"]) == "normal")
        check("sys.stdout in the app was never touched", sys.stdout is sys.__stdout__)

        # input(): the prompt shows, the typed line goes to the program
        node["blocks"][:] = [("assign_variable", {"variable": "name", "value": "input('Your name? ')"}),
                             ("print_output", {"value": "'Hi ' + name"})]
        app.update_generated_code()
        view.again()
        check("a prompt shows before anything is typed", wait(app, lambda: "Your name?" in view.contents()))
        check("the answer box is on while the program waits", str(view.entry["state"]) == "normal" and str(view.stop_btn["state"]) == "normal")
        view.entry.insert(0, "Ada")
        view.send()
        check("the typed answer is echoed and the program replies",
              wait(app, lambda: view.status_text == "Finished") and "Hi Ada" in view.contents())

        # a loop that never ends can be stopped
        node["blocks"][:] = [("loop_while", {"condition": "True", "_children": [("print_output", {"value": "'tick'"})]})]
        app.update_generated_code()
        view.again()
        check("a never-ending loop streams its output while running", wait(app, lambda: view.contents().count("tick") > 3) and view.run.running)
        view.stop()
        check("Stop ends the loop and says so", wait(app, lambda: view.status_text == "Stopped") and "Stopped" in view.contents())
        check("the window is still alive and usable after a stop", view.win.winfo_exists() and str(view.again_btn["state"]) == "normal")

        # errors
        node["blocks"][:] = [("print_output", {"value": "undefined_thing"})]
        app.update_generated_code()
        view.again()
        check("an error shows its traceback, not a silent blank window",
              wait(app, lambda: view.status_text.startswith("Exit code")) and "NameError" in view.contents() and "line" in view.contents())

        # two windows do not mix
        node["blocks"][:] = [("print_output", {"value": "'AAA'"})]
        app.update_generated_code()
        second = app.run_code()
        wait(app, lambda: second.status_text == "Finished")
        check("a second window has only its own output", "AAA" in second.contents() and "AAA" not in view.contents())

        # closing the window ends a running program
        node["blocks"][:] = [("loop_while", {"condition": "True", "_children": []})]
        app.update_generated_code()
        third = app.run_code()
        settle(app)
        proc = third.run.proc
        third.close()
        check("closing the window ends the program", wait(app, lambda: proc.poll() is not None, 10))
        check("no temp folder is left behind", third.run is None)
        second.close(); view.close()
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
