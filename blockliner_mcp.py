#!/usr/bin/env python3
"""Blockliner MCP bridge: lets an MCP client (Claude Code, Claude Desktop, ...) read and
change the project open in a running Blockliner. Standard library only.

It is a stdio MCP server. It does nothing by itself: it forwards each tool call to
the running Blockliner over a local, token-protected channel that the user switches
on in Blockliner (Tools > AI tools connection...). With the channel off or Blockliner
closed, every tool answers with a message saying so.

Add it to a client, for example:
    claude mcp add blockliner -- python3 /path/to/blockliner_mcp.py
The connection file is user_data/control.json next to this script; set
BLOCKLINER_CONTROL to use another path.
"""
import json
import os
import socket
import sys

SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL = "2024-11-05"
HERE = os.path.dirname(os.path.abspath(__file__))
OFF_MESSAGE = ("Blockliner is not accepting AI tools right now. Open Blockliner, choose Tools > "
               "AI tools connection... and switch it on.")

TOOLS = [
    {"name": "read_project",
     "description": "Read the project open in Blockliner: files, nodes, blocks, imports, and the block ids available for editing.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_blocks",
     "description": "List the block ids (with their parameters) that edit_project may use for the open language.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "edit_project",
     "description": ("Change the project, all-or-nothing. Operations: add_node {name, kind: function|category, parent?, "
                     "blocks?: [{block, params, children?}]}, add_block {node (node id), block, params, children?, index?}, "
                     "set_code {node, code}, rename_node {node, name}; add 'file' (index, default 0) to pick a file. "
                     "Needs edit access; the user may be asked to approve; one undo step in Blockliner."),
     "inputSchema": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object"}}}, "required": ["edits"]}},
    {"name": "undo", "description": "Undo the last change in Blockliner (needs edit access).",
     "inputSchema": {"type": "object", "properties": {}}},
]


def control_path():
    return os.environ.get("BLOCKLINER_CONTROL") or os.path.join(HERE, "user_data", "control.json")


def ask_blockliner(method, params, timeout=345):
    """The app's answer to one request: (True, result) or (False, message)."""
    try:
        with open(control_path(), encoding="utf-8") as f:
            info = json.load(f)
        sock = socket.create_connection((info["host"], info["port"]), timeout=5)
    except (OSError, ValueError, KeyError):
        return False, OFF_MESSAGE
    try:
        sock.settimeout(timeout)                       # an approval prompt can take a while
        sock.sendall((json.dumps({"id": 1, "token": info["token"], "method": method, "params": params}) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        msg = json.loads(data)
    except (OSError, ValueError):
        return False, "Blockliner did not answer. Is it still running?"
    finally:
        sock.close()
    if "error" in msg:
        return False, msg["error"].get("message", "refused")
    return True, msg.get("result")


def call_tool(name, arguments):
    if name not in {t["name"] for t in TOOLS}:
        return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
    ok, result = ask_blockliner(name, arguments if isinstance(arguments, dict) else {})
    text = json.dumps(result, ensure_ascii=False) if ok else str(result)
    return {"content": [{"type": "text", "text": text}], "isError": not ok}


def handle(msg):
    """The reply for one MCP message, or None for notifications."""
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "blockliner", "version": SERVER_VERSION}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        return {"jsonrpc": "2.0", "id": rid, "result": call_tool(params.get("name"), params.get("arguments"))}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is None:
        return None                                    # notifications (initialized, cancelled, ...)
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        reply = handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            print(json.dumps(reply, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
