"""What extensions may see of the project (pure, no Tk).

`snapshot(files)` is a plain, JSON-safe COPY of the open workspace: nothing in it
is a live object, so an extension can never change the project through it. Edits
go through project.write (a later step). The UI designer's tree and Blockliner's
derived data (references, wire kinds) are left out: they are rebuilt from the
rest and not part of a stable API.
"""
import json

API_PROJECT_VERSION = 1
MAX_DEPTH = 40                    # blocks inside blocks, as a guard against odd data


def _blocks(items, depth=0):
    out = []
    for item in items or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2 or depth > MAX_DEPTH:
            continue
        block_id, params = item[0], item[1] if isinstance(item[1], dict) else {}
        clean = {k: v for k, v in params.items() if not k.startswith("_")}
        entry = {"block": str(block_id), "params": json.loads(json.dumps(clean, default=str))}
        if params.get("_children"):
            entry["children"] = _blocks(params["_children"], depth + 1)
        out.append(entry)
    return out


def _nodes(nodes, depth=0):
    out = []
    for n in nodes or []:
        if not isinstance(n, dict) or depth > MAX_DEPTH:
            continue
        entry = {"id": str(n.get("id", "")), "name": str(n.get("name", "")), "kind": n.get("kind", "function"),
                 "has_ui": isinstance(n.get("ui"), dict)}
        if entry["kind"] == "function":
            entry["blocks"] = _blocks(n.get("blocks"))
        if n.get("child_nodes"):
            entry["children"] = _nodes(n["child_nodes"], depth + 1)
        out.append(entry)
    return out


def snapshot(files, active_index=0):
    """{"version", "active_file", "files": [{title, language, imports, active_node, nodes}]}"""
    return {
        "version": API_PROJECT_VERSION,
        "active_file": active_index,
        "files": [{"title": f.get("title"), "language": f.get("language", "?"),
                   "imports": [i for i in f.get("imports", []) if isinstance(i, str)],
                   "active_node": f.get("active_node_id"), "nodes": _nodes(f.get("nodes"))} for f in files],
    }


def fingerprint(snap):
    """A short text that changes when the project does (for the changed event)."""
    return json.dumps(snap, sort_keys=True, default=str)
