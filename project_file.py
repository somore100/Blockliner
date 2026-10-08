"""Whole-project save file (JSON, no Tk).

One file = one tab's file layer: language, the full node tree (nodes,
classes, categories, order, positions) and which node was active.
Version 2. Older saves (a bare block list, or {"language", "blocks"})
still load as a single "main" node.

Reserved for later (not written yet): "node_library" (custom/raw/prebuilt
nodes). Unknown top-level keys are ignored, so adding it won't break
old files.
"""
import json

from nodes_model import make_node, normalize_orders, default_active_node_id

FORMAT = "blockliner-project"
VERSION = 2
KINDS = ("function", "class", "category")


def _blocks_from_json(items, notes):
    """JSON turns (block_id, params) tuples into lists; turn them back.
    Bad entries are dropped with a note, never an exception."""
    out = []
    if not isinstance(items, (list, tuple)):
        return out
    for it in items:
        if (isinstance(it, (list, tuple)) and len(it) == 2
                and isinstance(it[0], str) and isinstance(it[1], dict)):
            params = dict(it[1])
            if "_children" in params:
                params["_children"] = _blocks_from_json(params["_children"], notes)
            out.append((it[0], params))
        else:
            notes.append("A damaged block was skipped.")
    return out


def _node_from_json(raw, seen_ids, notes):
    if not isinstance(raw, dict):
        notes.append("A damaged node was skipped.")
        return None
    name = raw.get("name")
    nid = raw.get("id")
    kind = raw.get("kind", "function")
    if not isinstance(name, str) or not name or kind not in KINDS:
        notes.append("A damaged node was skipped.")
        return None
    if not isinstance(nid, str) or not nid or nid in seen_ids:
        base = "".join(c if c.isalnum() or c == "_" else "_" for c in name) or "node"
        nid, n = base, 2
        while nid in seen_ids:
            nid = f"{base}_{n}"
            n += 1
    seen_ids.add(nid)
    node = make_node(
        name, node_id=nid, kind=kind,
        blocks=_blocks_from_json(raw.get("blocks"), notes) if kind == "function" else [],
        category=raw.get("category") if isinstance(raw.get("category"), str) else None,
        locked=bool(raw.get("locked", False)),
        node_type_id=raw.get("node_type_id") if isinstance(raw.get("node_type_id"), str) else None,
    )
    if "order" in raw and (raw["order"] is None or (isinstance(raw["order"], int)
                                                    and not isinstance(raw["order"], bool))):
        node["order"] = raw["order"]
    for key in ("canvas_x", "canvas_y", "x", "y"):
        if isinstance(raw.get(key), (int, float)) and not isinstance(raw.get(key), bool):
            node[key] = raw[key]
    if kind in ("class", "category"):
        kids = raw.get("child_nodes")
        for k in kids if isinstance(kids, list) else []:
            child = _node_from_json(k, seen_ids, notes)
            if child is not None:
                node["child_nodes"].append(child)
    return node


def build_project_data(language, nodes, active_node_id):
    """Plain dict ready for json.dump (references are derived, so left out)."""
    def clean(node):
        d = {k: v for k, v in node.items() if k not in ("references", "child_nodes")}
        d["child_nodes"] = [clean(c) for c in node.get("child_nodes", [])]
        return d
    return {
        "format": FORMAT,
        "version": VERSION,
        "language": language,
        "active_node_id": active_node_id,
        "nodes": [clean(n) for n in nodes],
    }


def parse_project_data(data, known_languages, fallback_language="python"):
    """-> (language, nodes, active_node_id, notes). Never raises on odd
    data; raises ValueError only when the file is not a project at all."""
    notes = []
    if isinstance(data, list):                      # oldest: bare block list
        data = {"language": fallback_language, "blocks": data}
    if not isinstance(data, dict):
        raise ValueError("This file is not a Blockliner project.")

    language = data.get("language")
    if language not in known_languages:
        if language is not None:
            notes.append(f"Unknown language '{language}' - using {fallback_language}.")
        language = fallback_language

    if isinstance(data.get("nodes"), list) and data["nodes"]:
        seen = set()
        nodes = [n for n in (_node_from_json(r, seen, notes) for r in data["nodes"]) if n]
        if not nodes:
            raise ValueError("The project has no readable nodes.")
    elif "blocks" in data:                          # old single-node format
        nodes = [make_node("main", node_id="main",
                           blocks=_blocks_from_json(data["blocks"], notes))]
        notes.append("Old save format: loaded as a single 'main' node.")
    else:
        raise ValueError("This file is not a Blockliner project.")

    normalize_orders(nodes)
    active = data.get("active_node_id")
    from nodes_model import find_node_by_id
    found = find_node_by_id(nodes, active) if isinstance(active, str) else None
    if found is None or found.get("kind", "function") != "function":
        active = default_active_node_id(nodes) or nodes[0]["id"]
    return language, nodes, active, notes


def dumps(language, nodes, active_node_id):
    return json.dumps(build_project_data(language, nodes, active_node_id), indent=2)


# ---- version 3: a whole workspace (tab) = several files ------------------

WORKSPACE_VERSION = 3


def build_workspace_data(files, active_index):
    """files: list of file dicts (title, language, nodes, active_node_id,
    optional canvas_x/canvas_y). Each file is saved like a version-2 project."""
    out = []
    for f in files:
        d = build_project_data(f.get("language", "python"), f["nodes"], f.get("active_node_id"))
        d.pop("format", None)
        d.pop("version", None)
        d["title"] = f.get("title")
        for key in ("canvas_x", "canvas_y"):
            if isinstance(f.get(key), (int, float)) and not isinstance(f.get(key), bool):
                d[key] = f[key]
        out.append(d)
    return {"format": FORMAT, "version": WORKSPACE_VERSION,
            "active_file": active_index, "files": out}


def parse_workspace_data(data, known_languages, fallback_language="python"):
    """-> (files, active_index, notes). Accepts version 3 (files list) and
    every older shape (one file). Raises ValueError only for non-projects."""
    notes = []
    if isinstance(data, dict) and isinstance(data.get("files"), list):
        files = []
        for raw in data["files"]:
            try:
                lang, nodes, active, n = parse_project_data(raw, known_languages, fallback_language)
            except ValueError:
                notes.append("A damaged file was skipped.")
                continue
            notes += n
            f = {"title": raw.get("title") if isinstance(raw.get("title"), str) and raw.get("title") else None,
                 "language": lang, "nodes": nodes, "active_node_id": active}
            for key in ("canvas_x", "canvas_y"):
                if isinstance(raw.get(key), (int, float)) and not isinstance(raw.get(key), bool):
                    f[key] = raw[key]
            files.append(f)
        if not files:
            raise ValueError("The project has no readable files.")
        ai = data.get("active_file")
        if not isinstance(ai, int) or isinstance(ai, bool) or not 0 <= ai < len(files):
            ai = 0
        return files, ai, notes
    lang, nodes, active, notes = parse_project_data(data, known_languages, fallback_language)
    return [{"title": None, "language": lang, "nodes": nodes, "active_node_id": active}], 0, notes


def dumps_workspace(files, active_index):
    return json.dumps(build_workspace_data(files, active_index), indent=2)
