"""Smallest useful Blockliner extension: speaks JSON lines on stdin/stdout.
See docs/design-extensions.md."""
import json
import sys

counter = 0
summary = "Reading the project..."
next_id = 10


def send(obj):
    print(json.dumps(obj), flush=True)


def show_panel():
    send({"id": 1, "method": "panel.set", "params": {"description": {
        "type": "column", "children": [
            {"type": "label", "text": "Hello from an extension", "style": "title"},
            {"type": "label", "text": summary, "style": "muted"},
            {"type": "label", "text": f"Button pressed {counter} times", "style": "muted"},
            {"type": "button", "text": "Press me", "command": "press"},
            {"type": "button", "text": "Add a demo node", "command": "add_node"}]}}})


def ask_project():
    global next_id
    next_id += 1
    send({"id": next_id, "method": "project.read", "params": {}})


def count_nodes(nodes):
    return sum(1 + count_nodes(n.get("children")) for n in nodes or [])


for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("event") == "hello":
        send({"event": "ready", "params": {"api": ["1.0"]}})
        show_panel()
        ask_project()
    elif msg.get("event") == "project.changed":
        ask_project()
    elif msg.get("event") == "command" and msg["params"].get("command") == "press":
        counter += 1
        send({"id": 2, "method": "notify", "params": {"text": f"Pressed {counter} times"}})
        show_panel()
    elif msg.get("event") == "command" and msg["params"].get("command") == "add_node":
        send({"id": 3, "method": "project.edit", "params": {"edits": [
            {"op": "add_node", "name": "hello_node",
             "blocks": [{"block": "print_output", "params": {"value": "\"Hi from an extension\""}}]}]}})
    elif msg.get("id") == 3 and "error" in msg:                                  # the edit was refused
        send({"id": 4, "method": "notify", "params": {"text": msg["error"]["message"]}})
    elif isinstance(msg.get("result"), dict) and "files" in msg["result"]:      # the project.read answer
        files = msg["result"]["files"]
        summary = f"{len(files)} file(s), {sum(count_nodes(f['nodes']) for f in files)} node(s)"
        show_panel()
    elif msg.get("event") == "shutdown":
        break
