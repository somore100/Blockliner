"""The MCP bridge against a real control server (loopback, no Tk, no network)."""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import control_server as C

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blockliner_mcp.py")

def session(control_path, messages):
    env = dict(os.environ, BLOCKLINER_CONTROL=control_path)
    p = subprocess.run([sys.executable, BRIDGE], input="\n".join(json.dumps(m) for m in messages) + "\n",
                       capture_output=True, text=True, env=env, timeout=30)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]

def main():
    seen = []
    def handler(method, params):
        seen.append((method, params))
        if method == "edit_project" and params.get("bad"):
            raise C.ControlError("invalid", "no such block")
        return {"method": method, "files": 1}
    srv = C.ControlServer(handler, access="read")
    port, token = srv.start()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "control.json")
        C.write_control_file(path, port, token, "read")
        out = session(path, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "read_project", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "edit_project", "arguments": {"edits": []}}},
            {"jsonrpc": "2.0", "id": 5, "method": "ping"},
            {"jsonrpc": "2.0", "id": 6, "method": "nope"},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "format_disk"}}])
        by = {m["id"]: m for m in out}
        check("it answers initialize with the client's protocol version and tool support", by[1]["result"]["protocolVersion"] == "2025-03-26" and "tools" in by[1]["result"]["capabilities"])
        check("notifications get no reply", len(out) == 7)
        check("it lists the four tools", {t["name"] for t in by[2]["result"]["tools"]} == {"read_project", "list_blocks", "edit_project", "undo"})
        r3 = by[3]["result"]
        check("a read goes through to the app", r3["isError"] is False and json.loads(r3["content"][0]["text"]) == {"method": "read_project", "files": 1})
        check("an edit at read access is an error result with the reason", by[4]["result"]["isError"] is True and "read-only" in by[4]["result"]["content"][0]["text"] and ("edit_project", {"edits": []}) not in seen)
        check("ping works, unknown methods are JSON-RPC errors", by[5]["result"] == {} and by[6]["error"]["code"] == -32601)
        check("an unknown tool is an error result", by[7]["result"]["isError"] is True)
        srv.access = "edit"
        out = session(path, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "edit_project", "arguments": {"edits": [{"op": "x"}]}}},
                             {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "edit_project", "arguments": {"bad": True}}}])
        check("an edit works once the user allows it", out[0]["result"]["isError"] is False and ("edit_project", {"edits": [{"op": "x"}]}) in seen)
        check("the app's refusal text reaches the agent", out[1]["result"]["isError"] is True and "no such block" in out[1]["result"]["content"][0]["text"])
        srv.stop()
        out = session(path, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_project"}}])
        check("with the channel off the tool says how to switch it on", out[0]["result"]["isError"] is True and "AI tools connection" in out[0]["result"]["content"][0]["text"])
        C.remove_control_file(path)
        out = session(path, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_project"}}])
        check("with no control file it says the same", "AI tools connection" in out[0]["result"]["content"][0]["text"])
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
