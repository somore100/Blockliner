"""Running a program in its own process (pure): streaming output, input(), errors, Stop, flooding, missing Python."""
import os, queue, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import program_runner as R

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

PY = os.environ.get("BLOCKLINER_TEST_PYTHON") or sys.executable

def collect(run, until=15, stop_on=None):
    """Everything the run reports, as (out, err, end_code)."""
    out, err, end = "", "", None
    deadline = time.time() + until
    while time.time() < deadline:
        try:
            kind, payload = run.events.get(timeout=0.2)
        except queue.Empty:
            continue
        if kind == "out": out += payload
        elif kind == "err": err += payload
        else:
            end = payload
            break
        if stop_on and stop_on(out, err):
            break
    return out, err, end

def main():
    check("the Settings command comes first, then the usual names", R.python_candidates("python3")[0] == ["python3"] and ["python"] in R.python_candidates("python3"))
    check("a made-up command falls back to the Python that runs Blockliner (from source)", R.find_python("no-such-python-xyz") == [sys.executable])
    check("a command with arguments is split", R.python_candidates("py -3")[0] == ["py", "-3"])

    r = R.ProgramRun("print('hello')\nprint('there')", PY).start()
    out, err, end = collect(r)
    check("output arrives and the run ends with code 0", out.split() == ["hello", "there"] and err == "" and end == 0)
    check("the temp folder is removed afterwards", (r.cleanup(), r.folder is None)[1])

    r = R.ProgramRun("import time\nprint('first', flush=True)\ntime.sleep(30)\nprint('never')", PY).start()
    out, err, end = collect(r, stop_on=lambda o, e: "first" in o)
    check("output shows while the program is still running", "first" in out and r.running)
    t0 = time.time(); r.stop()
    _o, _e, end = collect(r, until=10)
    check("Stop ends a sleeping program within the grace time", end is not None and not r.running and time.time() - t0 < 5 and r.stopped)
    r.cleanup()

    r = R.ProgramRun("while True:\n    pass", PY).start()
    time.sleep(0.5); r.stop()
    _o, _e, end = collect(r, until=10)
    check("Stop ends `while True` (the loop a beginner starts with)", end is not None and not r.running)
    r.cleanup()

    r = R.ProgramRun("name = input('Name? ')\nprint('Hi ' + name)", PY).start()
    out, err, end = collect(r, stop_on=lambda o, e: o.endswith("Name? "))
    check("the prompt shows before any newline", out == "Name? ")
    check("a typed line is delivered to input()", r.send_line("Ada") is True)
    out2, err, end = collect(r)
    check("the program continues with the answer", out2.strip() == "Hi Ada" and end == 0)
    check("sending to a finished program says so", r.send_line("x") is False)
    r.cleanup()

    r = R.ProgramRun("x = 1\nprint(undefined_name)", PY).start()
    out, err, end = collect(r)
    check("an error shows a traceback with the line and a readable file name", "NameError" in err and "line 2" in err and R.PROGRAM_NAME in err and "blockliner_run_" not in err and end == 1)
    r.cleanup()

    r = R.ProgramRun("import sys\nprint('before')\nsys.exit(3)", PY).start()
    out, err, end = collect(r)
    check("sys.exit ends only the program, with its code", out.strip() == "before" and end == 3)
    r.cleanup()

    r = R.ProgramRun("print('café → ✓')", PY).start()
    out, err, end = collect(r)
    check("non-ASCII text arrives intact", out.strip() == "café → ✓")
    r.cleanup()

    r = R.ProgramRun("while True:\n    print('x' * 200)", PY, queue_size=50).start()
    time.sleep(1.0)
    check("a program that floods the output waits instead of growing memory", r.events.qsize() <= 50 and r.running)
    r.stop(force=True)
    r.cleanup()

    r = R.ProgramRun("import os\nopen('made_by_program.txt', 'w').write('x')\nprint(os.getcwd())", PY).start()
    out, err, end = collect(r)
    check("it runs in its own private folder by default", os.path.basename(out.strip()).startswith("blockliner_run_"))
    r.cleanup()

    try:
        import unittest.mock as m
        with m.patch.object(R, "find_python", return_value=None):
            R.ProgramRun("print(1)", "nope").start()
        raised = False
    except R.RunnerError as e:
        raised = "Settings" in str(e)
    check("no Python found: a clear message, not a crash", raised)

    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
