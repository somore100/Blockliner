"""AI assistant for Blockliner: a chat panel whose model can read the project and
edit it through the extension API. Standard library only.

The model comes from an HTTP API you choose: by default Anthropic's Messages API
with YOUR key (stored through the secrets API, never in a project). Settings
(saved with the settings API): "model" and "api_base".
"""
import json
import sys
import threading
import urllib.error
import urllib.request

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BASE = "https://api.anthropic.com"
MAX_ROUNDS = 8
MAX_TOOL_TEXT = 60000

SYSTEM = (
    "You are an assistant inside Blockliner, a visual block-based code editor. A project is files, and a file is "
    "nodes (functions, or categories that hold nodes); a function node holds blocks. Call read_project first: it "
    "lists the files, nodes and blocks, and 'available_blocks' lists the block ids you may use for the open "
    "language with their parameters. Change the project only with edit_project, and only with block ids from "
    "available_blocks. Keep changes small and tell the user briefly what you did. Every change can be undone "
    "by the user.")

TOOLS = [
    {"name": "read_project", "description": "Read the open project: files, nodes, blocks, imports and the available block ids.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "edit_project", "description": (
        "Change the project. Pass a list of operations, applied all-or-nothing. Operations: "
        "add_node {name, kind: function|category, parent?, blocks?: [{block, params, children?}]}, "
        "add_block {node (node id), block, params, children?, index?}, "
        "set_code {node, code} (turns code text into blocks), rename_node {node, name}. "
        "Add 'file' (index, default 0) to choose the file."),
     "input_schema": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object"}}}, "required": ["edits"]}},
]

out_lock = threading.Lock()
rpc_lock = threading.Lock()
waiting = {}
next_id = [100]
state = {"chat": [], "messages": [], "busy": False, "status": "", "has_key": None}


def send(obj):
    with out_lock:
        print(json.dumps(obj), flush=True)


def call(method, params, timeout=30):
    """Ask Blockliner and wait for the answer: (True, result) or (False, error text)."""
    with rpc_lock:
        next_id[0] += 1
        rid = next_id[0]
        box = {"event": threading.Event()}
        waiting[rid] = box
    send({"id": rid, "method": method, "params": params})
    if not box["event"].wait(timeout):
        waiting.pop(rid, None)
        return False, "Blockliner did not answer in time"
    msg = box["msg"]
    if "error" in msg:
        return False, msg["error"].get("message", "refused")
    return True, msg.get("result")


def feed(msg):
    box = waiting.pop(msg.get("id"), None)
    if box is not None:
        box["msg"] = msg
        box["event"].set()


# ---- the panel ---------------------------------------------------------------------
def show_panel():
    if state["has_key"] is None:
        ok, res = call("secrets.get", {"name": "api_key"})
        state["has_key"] = bool(ok and res and res.get("value"))
    if not state["has_key"]:
        children = [
            {"type": "label", "text": "AI assistant", "style": "title"},
            {"type": "label", "text": "Paste your API key. It is kept in Blockliner's protected extension data, never in a project.", "style": "muted"},
            {"type": "input", "id": "key", "secret": True, "label": "API key", "command": "save_key", "button": "Save"}]
    else:
        children = [
            {"type": "label", "text": "AI assistant", "style": "title"},
            {"type": "text", "text": "\n\n".join(state["chat"]) or "Ask me to read or change your project.", "height": 20, "follow": True},
            {"type": "label", "text": state["status"], "style": "muted"},
            {"type": "input", "id": "msg", "command": "send", "button": "Send"},
            {"type": "row", "children": [{"type": "button", "text": "Clear chat", "command": "clear"}]},
            {"type": "button", "text": "Forget my API key", "command": "forget_key"}]
    send({"id": 1, "method": "panel.set", "params": {"description": {"type": "column", "children": children}}})


def say(who, text):
    state["chat"].append(f"{who}: {text}")
    show_panel()


# ---- the model ---------------------------------------------------------------------
def setting(key, default):
    ok, res = call("settings.get", {"key": key})
    return res["value"] if ok and res and res.get("value") else default


def ask_model(messages):
    ok, res = call("secrets.get", {"name": "api_key"})
    key = res.get("value") if ok and res else None
    if not key:
        raise RuntimeError("no API key saved")
    body = json.dumps({"model": setting("model", DEFAULT_MODEL), "max_tokens": 4096, "system": SYSTEM,
                       "tools": TOOLS, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(setting("api_base", DEFAULT_BASE).rstrip("/") + "/v1/messages", data=body, method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"the model API answered {e.code}: {detail}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"could not reach the model API ({e})")


def run_tool(name, args):
    if name == "read_project":
        ok, res = call("project.read", {})
    elif name == "edit_project":
        ok, res = call("project.edit", {"edits": args.get("edits")})
        if ok:
            say("Blockliner", "; ".join(res.get("summary", [])) or "changed")
    else:
        return True, f"unknown tool {name}"
    text = json.dumps(res) if ok else f"error: {res}"
    return (not ok), text[:MAX_TOOL_TEXT]


def chat_turn(user_text):
    state["busy"] = True
    state["status"] = "Thinking..."
    say("You", user_text)
    messages = state["messages"]
    messages.append({"role": "user", "content": user_text})
    try:
        for _ in range(MAX_ROUNDS):
            reply = ask_model(messages)
            content, results = [], []
            for block in reply.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    content.append({"type": "text", "text": block["text"]})
                    say("AI", block["text"])
                elif block.get("type") == "tool_use":
                    content.append({"type": "tool_use", "id": block["id"], "name": block["name"], "input": block.get("input", {})})
                    state["status"] = f"Using {block['name']}..."
                    show_panel()
                    is_error, text = run_tool(block["name"], block.get("input") or {})
                    results.append({"type": "tool_result", "tool_use_id": block["id"], "content": text, "is_error": is_error})
            messages.append({"role": "assistant", "content": content})
            if not results:
                break
            messages.append({"role": "user", "content": results})
    except RuntimeError as e:
        say("Error", str(e))
    finally:
        state["busy"] = False
        state["status"] = ""
        show_panel()


def on_command(params):
    command, value = params.get("command"), (params.get("value") or "").strip()
    if command == "save_key" and value:
        ok, res = call("secrets.set", {"name": "api_key", "value": value})
        state["has_key"] = bool(ok)
        show_panel()
    elif command == "forget_key":
        call("secrets.set", {"name": "api_key", "value": None})
        state["has_key"], state["chat"], state["messages"] = False, [], []
        show_panel()
    elif command == "clear":
        state["chat"], state["messages"] = [], []
        show_panel()
    elif command == "send" and value and not state["busy"]:
        threading.Thread(target=chat_turn, args=(value,), daemon=True).start()


for line in sys.stdin:
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    event = msg.get("event")
    if event == "hello":
        send({"event": "ready", "params": {"api": ["1.0"]}})
        threading.Thread(target=show_panel, daemon=True).start()
    elif event == "command":
        threading.Thread(target=on_command, args=(msg.get("params") or {},), daemon=True).start()
    elif event == "shutdown":
        break
    elif "id" in msg:
        feed(msg)
