"""Smallest useful Blockliner extension: speaks JSON lines on stdin/stdout.
See docs/design-extensions.md."""
import json
import sys

counter = 0


def send(obj):
    print(json.dumps(obj), flush=True)


def show_panel():
    send({"id": 1, "method": "panel.set", "params": {"description": {
        "type": "column", "children": [
            {"type": "label", "text": "Hello from an extension", "style": "title"},
            {"type": "label", "text": f"Button pressed {counter} times", "style": "muted"},
            {"type": "button", "text": "Press me", "command": "press"}]}}})


for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("event") == "hello":
        send({"event": "ready", "params": {"api": ["1.0"]}})
        show_panel()
    elif msg.get("event") == "command" and msg["params"].get("command") == "press":
        counter += 1
        send({"id": 2, "method": "notify", "params": {"text": f"Pressed {counter} times"}})
        show_panel()
    elif msg.get("event") == "shutdown":
        break
