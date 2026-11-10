"""The local control channel (loopback sockets, no Tk)."""
import json, os, socket, stat, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import control_server as C

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def ask(port, msg, raw=None):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(raw if raw is not None else (json.dumps(msg) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk: break
        data += chunk
    s.close()
    return json.loads(data) if data else None

def main():
    calls = []
    def handler(method, params):
        calls.append((method, params))
        if method == "edit_project" and params.get("fail"):
            raise C.ControlError("invalid", "bad edit")
        if method == "undo" and params.get("boom"):
            raise RuntimeError("boom")
        return {"echo": method}
    srv = C.ControlServer(handler, access="read")
    check("not running before start", not srv.running)
    port, token = srv.start()
    check("it listens on a free local port with a token", srv.running and port > 0 and len(token) >= 20 and srv.start() == (port, token))
    r = ask(port, {"id": 1, "token": token, "method": "read_project", "params": {}})
    check("a read with the token works", r == {"id": 1, "result": {"echo": "read_project"}})
    check("a wrong token is refused and the handler not called", ask(port, {"id": 2, "token": "nope", "method": "read_project"})["error"]["code"] == "unauthorized" and len(calls) == 1)
    check("a missing token is refused", ask(port, {"id": 3, "method": "read_project"})["error"]["code"] == "unauthorized")
    check("an edit is denied at read access", ask(port, {"id": 4, "token": token, "method": "edit_project", "params": {"edits": []}})["error"]["code"] == "denied" and len(calls) == 1)
    srv.access = "edit"
    check("the same edit works once the user allows editing", ask(port, {"id": 5, "token": token, "method": "edit_project", "params": {"edits": []}})["result"] == {"echo": "edit_project"})
    check("a handler's refusal reaches the caller with its code", ask(port, {"id": 6, "token": token, "method": "edit_project", "params": {"fail": True}})["error"] == {"code": "invalid", "message": "bad edit"})
    check("a handler bug is an error answer, the server stays up", ask(port, {"id": 7, "token": token, "method": "undo", "params": {"boom": True}})["error"]["code"] == "failed"
          and ask(port, {"id": 8, "token": token, "method": "read_project"})["result"])
    check("unknown methods are refused", ask(port, {"id": 9, "token": token, "method": "rm_rf"})["error"]["code"] == "unknown_method")
    check("junk is answered, not fatal", ask(port, None, raw=b"not json\n")["error"]["code"] == "bad_request")
    big = ask(port, None, raw=b"x" * (C.MAX_LINE + 10) + b"\n")
    check("an oversized request is refused", big is not None and big["error"]["code"] == "too_big")
    check("the log records outcomes without params", [m for _t, m, _o in srv.log][:2] == ["read_project", "read_project"] and "unauthorized" in [o for _t, _m, o in srv.log])
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall((json.dumps({"id": 1, "token": token, "method": "read_project"}) + "\n" + json.dumps({"id": 2, "token": token, "method": "read_project"}) + "\n").encode())
    time.sleep(0.3); data = s.recv(65536).decode(); s.close()
    check("one connection can send several requests", data.count("\n") == 2)
    srv.stop()
    check("stopping ends it and forgets the token", not srv.running and srv.token == "")
    refused = False
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    except OSError:
        refused = True
    check("nothing listens after stop", refused)
    port2, token2 = srv.start()
    check("a new start makes a new token", token2 != token); srv.stop()

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sub", "control.json")
        C.write_control_file(path, 1234, "tok", "read")
        check("the control file is owner-only and readable back", (os.name == "nt" or stat.S_IMODE(os.stat(path).st_mode) == 0o600) and C.read_control_file(path)["port"] == 1234)
        C.remove_control_file(path)
        check("removing it turns the channel off for the bridge", C.read_control_file(path) is None)
        open(path, "w").write("{"); 
        check("a damaged file is not usable", C.read_control_file(path) is None)
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
