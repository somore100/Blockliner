"""Extensions that ship with Blockliner (pure, no Tk). Each builds what its panel
shows, or answers a command, from plain data the app hands over, so they are
tested without a window. The app draws the result (see ui_extensions.py).

A panel is a small widget description, the same kind an outside extension would
send:  {"type": "column" | "row", "children": [...]}  with leaves
  {"type": "label", "text": "...", "style": "title" | "muted" | None}
  {"type": "button", "text": "...", "command": "name"}
"""


def _count_blocks(blocks):
    total = 0
    for item in blocks or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        total += 1
        params = item[1] if isinstance(item[1], dict) else {}
        total += _count_blocks(params.get("_children"))
    return total


def _walk_nodes(nodes):
    for node in nodes or []:
        yield node
        yield from _walk_nodes(node.get("child_nodes"))


def project_stats(files):
    """Counts for a list of file dicts (the workspace's tabs)."""
    stats = {"files": len(files), "nodes": 0, "blocks": 0, "imports": 0, "languages": {}}
    for f in files:
        stats["languages"][f.get("language", "?")] = stats["languages"].get(f.get("language", "?"), 0) + 1
        stats["imports"] += len([n for n in f.get("imports", []) if isinstance(n, str)])
        for node in _walk_nodes(f.get("nodes")):
            if node.get("kind", "function") == "function":
                stats["nodes"] += 1
                stats["blocks"] += _count_blocks(node.get("blocks"))
    return stats


def _row(label, value):
    return {"type": "row", "children": [{"type": "label", "text": label, "style": "muted"},
                                         {"type": "label", "text": str(value)}]}


def statistics_panel(files):
    s = project_stats(files)
    langs = ", ".join(f"{k} ({v})" for k, v in sorted(s["languages"].items())) or "-"
    return {"type": "column", "children": [
        {"type": "label", "text": "This project", "style": "title"},
        _row("Files", s["files"]), _row("Nodes", s["nodes"]), _row("Blocks", s["blocks"]), _row("Imports", s["imports"]),
        {"type": "label", "text": "Languages", "style": "muted"},
        {"type": "label", "text": langs},
        {"type": "button", "text": "Refresh", "command": "refresh"},
    ]}


def run_command(builtin, command, context):
    """Answer a command: returns {"clipboard": text, "notify": text} (keys optional)."""
    if builtin == "copy_code" and command == "copy":
        code = context.get("code", "")
        lines = len([ln for ln in code.splitlines() if ln.strip()])
        return {"clipboard": code, "notify": f"Copied {lines} lines of code."}
    return {}


PANELS = {"statistics": statistics_panel}
