"""What extensions may see of the project (pure, no Tk).

`snapshot(files)` is a plain, JSON-safe COPY of the open workspace: nothing in it
is a live object, so an extension can never change the project through it. Edits
go through project.write (a later step). The UI designer's tree and Blockliner's
derived data (references, wire kinds) are left out: they are rebuilt from the
rest and not part of a stable API.
"""
import copy
import json
import uuid

from nodes_model import find_node_by_id, make_node, next_order

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


# ---- project.write ---------------------------------------------------------------
MAX_OPS = 200
MAX_NEW_BLOCKS = 5000
MAX_NAME = 60
MAX_CODE = 100000


class EditError(Exception):
    """An edit request was refused; nothing was changed."""


def _text_params(params, wanted, where):
    """Params of a new block: every value text, only names the block declares,
    missing ones filled with the block's defaults."""
    if not isinstance(params, dict):
        raise EditError(f"{where}: params must be an object")
    out = dict(wanted)
    for key, value in params.items():
        if key not in wanted:
            raise EditError(f"{where}: unknown parameter '{key}'")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise EditError(f"{where}: parameter '{key}' must be text or a number")
        out[key] = str(value)
    return out


def _new_blocks(entries, language, known, counter, where, depth=0):
    if not isinstance(entries, list) or depth > MAX_DEPTH:
        raise EditError(f"{where}: blocks must be a list")
    out = []
    for i, e in enumerate(entries):
        here = f"{where}[{i}]"
        if not isinstance(e, dict) or not isinstance(e.get("block"), str):
            raise EditError(f"{here}: needs a 'block' name")
        wanted = known.get(language, {}).get(e["block"])
        if wanted is None:
            raise EditError(f"{here}: there is no block '{e['block']}' for {language}")
        params = _text_params(e.get("params") or {}, wanted, here)
        if e.get("children"):
            params["_children"] = _new_blocks(e["children"], language, known, counter, here + ".children", depth + 1)
        counter[0] += 1
        if counter[0] > MAX_NEW_BLOCKS:
            raise EditError(f"too many new blocks (most {MAX_NEW_BLOCKS} at once)")
        out.append((e["block"], params))
    return out


def _file(files, op):
    index = op.get("file", 0)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(files):
        raise EditError(f"there is no file {index!r}")
    return files[index]


def _function_node(file, op, key="node"):
    node = find_node_by_id(file["nodes"], op.get(key))
    if node is None:
        raise EditError(f"there is no node {op.get(key)!r} in that file")
    return node


def apply_edits(files, edits, known_blocks, code_to_blocks=None, id_factory=None):
    """Apply a list of edit operations to a COPY of `files` (the caller swaps it
    in only when this returns). Returns (new_files, summary lines); raises
    EditError, changing nothing, when anything is wrong.

    Operations (each a dict with "op"):
      add_node     {file, name, kind: "function" | "category", parent?, blocks?}
      add_block    {file, node, block, params?, children?, index?}
      set_code     {file, node, code}      (turns the code into blocks like Paste Code)
      rename_node  {file, node, name}
    `known_blocks` is {language: {block id: {param: default}}}; `code_to_blocks`
    (language, text) -> blocks does the set_code conversion."""
    if not isinstance(edits, list) or not edits:
        raise EditError("there is nothing to do")
    if len(edits) > MAX_OPS:
        raise EditError(f"too many operations (most {MAX_OPS} at once)")
    new_id = id_factory or (lambda: str(uuid.uuid4())[:8])
    work = copy.deepcopy(files)
    summary, counter = [], [0]
    for n, op in enumerate(edits, 1):
        where = f"operation {n}"
        if not isinstance(op, dict):
            raise EditError(f"{where}: must be an object")
        kind = op.get("op")
        if kind == "add_node":
            f = _file(work, op)
            name = str(op.get("name", "")).strip()
            if not name or len(name) > MAX_NAME:
                raise EditError(f"{where}: the node needs a name (1 to {MAX_NAME} characters)")
            node_kind = op.get("kind", "function")
            if node_kind not in ("function", "category"):
                raise EditError(f"{where}: kind must be 'function' or 'category'")
            siblings = f["nodes"]
            if op.get("parent") is not None:
                parent = find_node_by_id(f["nodes"], op["parent"])
                if parent is None or parent.get("kind") not in ("class", "category"):
                    raise EditError(f"{where}: the parent must be a class or category node")
                siblings = parent.setdefault("child_nodes", [])
            blocks = _new_blocks(op.get("blocks") or [], f["language"], known_blocks, counter, f"{where}.blocks") \
                if node_kind == "function" else None
            if node_kind == "category":
                node = make_node(name, node_id=new_id(), kind="category", child_nodes=[])
            else:
                node = make_node(name, node_id=new_id(), blocks=blocks, order=next_order(f["nodes"]))
            siblings.append(node)
            summary.append(f"Added {node_kind} node '{name}'" + (f" with {len(blocks)} block(s)" if blocks else ""))
        elif kind == "add_block":
            f = _file(work, op)
            node = _function_node(f, op)
            if node.get("kind", "function") != "function":
                raise EditError(f"{where}: blocks can only go into a function node")
            blocks = _new_blocks([op], f["language"], known_blocks, counter, where)
            index = op.get("index")
            target = node.setdefault("blocks", [])
            if index is None:
                target.extend(blocks)
            elif isinstance(index, int) and not isinstance(index, bool) and 0 <= index <= len(target):
                target[index:index] = blocks
            else:
                raise EditError(f"{where}: 'index' must be between 0 and {len(target)}")
            summary.append(f"Added a '{op['block']}' block to '{node['name']}'")
        elif kind == "set_code":
            f = _file(work, op)
            node = _function_node(f, op)
            code = op.get("code")
            if not isinstance(code, str) or len(code) > MAX_CODE:
                raise EditError(f"{where}: 'code' must be text (most {MAX_CODE} characters)")
            if node.get("kind", "function") != "function" or code_to_blocks is None:
                raise EditError(f"{where}: code can't be set on this node")
            blocks = code_to_blocks(f["language"], code)
            node["blocks"] = list(blocks)
            summary.append(f"Replaced the code of '{node['name']}' ({len(blocks)} block(s))")
        elif kind == "rename_node":
            f = _file(work, op)
            node = _function_node(f, op)
            name = str(op.get("name", "")).strip()
            if not name or len(name) > MAX_NAME:
                raise EditError(f"{where}: the node needs a name (1 to {MAX_NAME} characters)")
            summary.append(f"Renamed '{node['name']}' to '{name}'")
            node["name"] = name
        else:
            raise EditError(f"{where}: unknown operation {kind!r}")
    return work, summary
