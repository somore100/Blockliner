"""A tiny extension used by tests/test_ext_runner.py: behaviour chosen by argv[1]."""
import json, sys, time
mode = sys.argv[1]

def send(o): print(json.dumps(o), flush=True)
def log(t): print(t, file=sys.stderr, flush=True)

if mode == "silent":
    time.sleep(30)
for line in sys.stdin:
    msg = json.loads(line)
    ev = msg.get("event")
    if ev == "hello":
        if mode == "oldapi":
            send({"event": "ready", "params": {"api": ["0.9"]}})
        else:
            send({"event": "ready", "params": {"api": ["1.0"]}})
        if mode == "crash":
            sys.exit(3)
    elif ev == "command":
        send({"id": 1, "method": "notify", "params": {"text": "hi " + msg["params"].get("command", "")}})
        send({"id": 2, "method": "project.read", "params": {}})
        send({"id": 3, "method": "no.such", "params": {}})
        send({"event": "log", "params": {"text": "an event"}})
        print("not json at all", flush=True)
    elif "id" in msg:
        log("answer " + json.dumps(msg))
    elif ev == "shutdown":
        log("bye")
        sys.exit(0)
