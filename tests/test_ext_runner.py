"""Running extensions: start, hello, permissions, timeouts, restarts (no Tk; real child processes)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ext_runner as R

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_ext", "fake.py")

def wait(cond, secs=3.0):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.02)
    return cond()

def main():
    seen = []
    def handler(ext_id, method, params, is_event):
        seen.append((method, is_event, params))
        if method == "notify":
            return {"shown": True}
        raise R.ExtensionError("nope", "not available yet")

    def proc(mode, perms, **kw):
        return R.ExtensionProcess("me/fake", HERE, [sys.executable, FAKE, mode], perms, handler, ready_timeout=2.0, stop_timeout=1.0, **kw)

    p = proc("good", ["ui.notify"])
    check("a good extension starts and answers hello", p.start() and p.state == "running" and p.supported_api == ["1.0"])
    p.send_event("command", {"command": "go"})
    check("an allowed request reaches the handler", wait(lambda: ("notify", False, {"text": "hi go"}) in seen))
    check("a request without its permission is denied, and the extension is told",
          wait(lambda: any('"denied"' in line for line in p.log)) and not any(m == "project.read" for m, _e, _p in seen))
    check("an unknown method is refused", wait(lambda: any("unknown_method" in line for line in p.log)))
    check("events from the extension reach the handler", wait(lambda: ("log", True, {"text": "an event"}) in seen))
    check("junk lines are logged, not fatal", wait(lambda: any("not JSON" in line for line in p.log)) and p.alive())
    t0 = time.time(); p.stop()
    check("stop asks politely and the program ends quickly", not p.alive() and time.time() - t0 < 1.5 and p.state == "stopped")
    check("the extension's own error output is kept as a log", any("bye" in line for line in p.log))

    q = proc("silent", [])
    t0 = time.time()
    check("no hello answer: fails after the timeout, never hangs", not q.start() and q.state == "failed" and "hello" in q.note and time.time() - t0 < 4)
    check("the silent program was stopped", not q.alive())
    o = proc("oldapi", [])
    check("a mismatching API version fails cleanly", not o.start() and "0.9" in o.note and not o.alive())
    bad = R.ExtensionProcess("me/x", HERE, ["/nonexistent/program"], [], handler)
    check("a program that can't start is a failure, not a crash", not bad.start() and bad.state == "failed" and "could not start" in bad.note)

    host = R.Host(handler, max_restarts=2, ready_timeout=2.0, stop_timeout=1.0)
    check("host starts one", host.start("me/crashy", HERE, [sys.executable, FAKE, "crash"], []))
    check("a crash is noticed", wait(lambda: not host.procs["me/crashy"].alive()))
    news = host.check()
    check("it is restarted and the user can be told", news and news[0][1] == "restarted" and host.restarts["me/crashy"] == 1)
    wait(lambda: not host.procs["me/crashy"].alive()); host.check()
    wait(lambda: not host.procs["me/crashy"].alive()); last = host.check()
    check("after the restart limit it stays off", last and "turned off" in last[0][1] and host.status("me/crashy")["state"] == "failed")
    host.stop_all()
    check("stop_all stops everything", host.procs == {} and host.status("me/crashy")["state"] == "stopped")
    h2 = R.Host(handler, ready_timeout=2.0, stop_timeout=1.0)
    h2.start("me/good", HERE, [sys.executable, FAKE, "good"], ["ui.notify"])
    check("send_event goes to a running extension only", h2.send_event("me/good", "command", {"command": "x"}) and not h2.send_event("me/none", "command"))
    h2.stop_all()
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
