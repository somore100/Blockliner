"""The AI assistant example, end to end against a stub model server (no network, no key)."""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ext_runner as R
import extensions_api as A

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

seen = {"headers": [], "bodies": []}
SCRIPT = [
    {"content": [{"type": "text", "text": "Let me look."}, {"type": "tool_use", "id": "t1", "name": "read_project", "input": {}}]},
    {"content": [{"type": "tool_use", "id": "t2", "name": "edit_project", "input": {"edits": [
        {"op": "add_node", "name": "greeter", "blocks": [{"block": "print", "params": {"value": "'hi'"}}]}]}}]},
    {"content": [{"type": "text", "text": "Done: I added greeter."}]},
]

class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen["headers"].append({k.lower(): v for k, v in self.headers.items()}); seen["bodies"].append(body)
        reply = SCRIPT[min(len(seen["bodies"]) - 1, len(SCRIPT) - 1)]
        data = json.dumps(reply).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)

def wait(cond, secs=8.0):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.05)
    return cond()

def main():
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    files = [{"title": "m", "language": "python", "nodes": [{"id": "n1", "name": "main", "kind": "function", "blocks": []}]}]
    known = {"python": {"print": {"value": '"Hello"'}}}
    avail = {"python": {"print": {"name": "Print", "params": {"value": '"Hello"'}}}}
    secrets, panels, store = {"api_key": "test-key"}, [], {"api_base": base}

    def handler(ext_id, method, params, is_event):
        if is_event: return None
        if method == "panel.set": panels.append(json.dumps(params["description"])); return {"ok": True}
        if method == "project.read": return A.snapshot(files, 0, avail)
        if method == "project.edit":
            try:
                new, summary = A.apply_edits(files, params["edits"], known); files[:] = new; return {"ok": True, "summary": summary}
            except A.EditError as e: raise R.ExtensionError("invalid", str(e))
        if method == "settings.get": return {"value": store.get(params["key"])}
        if method == "secrets.get": return {"value": secrets.get(params["name"])}
        if method == "secrets.set":
            secrets[params["name"]] = params["value"]; return {"ok": True}
        return {}

    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "examples", "extension-assistant")
    manifest = json.load(open(os.path.join(folder, "extension.json")))
    host = R.Host(handler, ready_timeout=5, stop_timeout=2)
    check("the assistant starts", host.start("example/assistant", folder, [sys.executable, "main.py"], manifest["permissions"]))
    check("with a saved key it shows the chat panel", wait(lambda: any('"id": "msg"' in p for p in panels)))
    host.send_event("example/assistant", "command", {"command": "send", "value": "add a greeter node"})
    check("the model is asked with the key and tools", wait(lambda: len(seen["bodies"]) >= 3)
          and seen["headers"][0].get("x-api-key") == "test-key" and {t["name"] for t in seen["bodies"][0]["tools"]} == {"read_project", "edit_project"})
    check("the model got the project including the block ids it may use", any('available_blocks' in json.dumps(b["messages"]) for b in seen["bodies"][1:2]))
    check("its edit changed the project", wait(lambda: [n["name"] for n in files[0]["nodes"]] == ["main", "greeter"]) and files[0]["nodes"][1]["blocks"] == [("print", {"value": "'hi'"})])
    check("the tool result went back to the model", any(m["role"] == "user" and isinstance(m["content"], list) and m["content"][0].get("type") == "tool_result" for m in seen["bodies"][2]["messages"]))
    check("the final answer is shown in the panel", wait(lambda: any("Done: I added greeter." in p for p in panels)))
    host.send_event("example/assistant", "command", {"command": "forget_key"})
    check("forgetting the key removes it and asks for a new one", wait(lambda: secrets.get("api_key") is None and any('"id": "key"' in p for p in panels[-3:])))
    host.stop_all(); server.shutdown()
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
