"""Node templates (no Tk): saved node structures you can drop in instead of
building from scratch.

Folder layout (one root per place it can live; the app looks in the bundled
one and in the user one, which are the same folder when running from source):

    nodes/
      general/            works in every language (use only blocks that exist
        custom/*.json     in all of them, e.g. comment, print_output)
        prebuilt/*.json
      python/             one folder per language, same shape
        custom/*.json     made by the user (writable)
        prebuilt/*.json   ships with the app (modules, e.g. input handling)

A "raw" node is simply a blank node (no template) and needs no file.

File format (version 1):

    {"format": "blockliner-node", "version": 1,
     "name": "Login check", "description": "...",
     "kind": "function" | "class",
     "variables": [{"name": "user_field", "label": "Username field", "default": "username"}],
     "blocks": [["block_id", {"param": "value", "_children": [...]}], ...],
     "child_nodes": [ ...nodes... ]            # class kind only
    }

Anywhere a string appears (node name, block params) {{variable}} is replaced
by the value you give when adding the node. The pseudo block "@raw" with
{"code": "line1\\nline2"} becomes one raw-code block per line in whichever
language it is added to.
"""
import copy
import json
import os
import re

from nodes_model import make_node
from project_file import _blocks_from_json

FORMAT = "blockliner-node"
VERSION = 1
KINDS = ("function", "class")
FOLDER_KINDS = ("custom", "prebuilt")
GENERAL = "general"
RAW_PSEUDO_BLOCK = "@raw"

_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SAFE_SCOPE = re.compile(r"^[a-z0-9_]+$")
MAX_VARIABLES = 20


# ---------------------------------------------------------------- variables

def _strings(obj):
    """Every string inside nested lists/tuples/dicts, in order."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _node_strings(node):
    yield node.get("name", "")
    yield from _strings(node.get("blocks", []))
    for child in node.get("child_nodes", []):
        yield from _node_strings(child)


def scan_variables(node_or_template):
    """Names used as {{name}} anywhere in a node/template, first-use order."""
    seen, out = set(), []
    for s in _node_strings(node_or_template):
        for m in _VAR.finditer(s):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                out.append(m.group(1))
    return out[:MAX_VARIABLES]


def _substitute(obj, values):
    if isinstance(obj, str):
        return _VAR.sub(lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, values) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return tuple(_substitute(v, values) for v in obj)
    if isinstance(obj, list):
        return [_substitute(v, values) for v in obj]
    return obj


# ----------------------------------------------------------------- building

def _clean_node(node):
    """Strip what only makes sense inside one file: id, position, order,
    references, lock, entry-point link."""
    kind = node.get("kind", "function")
    out = {"name": node.get("name", "Node"), "kind": kind}
    if kind == "function":
        out["blocks"] = json.loads(json.dumps(node.get("blocks", [])))
    else:
        out["child_nodes"] = [_clean_node(c) for c in node.get("child_nodes", [])
                              if c.get("kind", "function") in KINDS]
    return out


def build_template(node, name=None, description="", defaults=None):
    """Template dict from a live function/class node. Variables are the
    {{names}} found in it; `defaults` maps name -> default text."""
    if node.get("kind", "function") not in KINDS:
        raise ValueError("Only function and class nodes can be saved as a template.")
    clean = _clean_node(node)
    names = scan_variables(clean)
    defaults = defaults or {}
    t = {"format": FORMAT, "version": VERSION,
         "name": (name or "").strip() or str(node.get("name") or "").strip() or "Node",
         "description": (description or "").strip(),
         "kind": clean["kind"],
         "variables": [{"name": n, "label": n.replace("_", " ").capitalize(),
                        "default": str(defaults.get(n, ""))} for n in names]}
    if clean["kind"] == "function":
        t["blocks"] = clean["blocks"]
    else:
        t["child_nodes"] = clean["child_nodes"]
    return t


# ------------------------------------------------------------------ parsing

def _parse_node(raw, notes, depth=0):
    if not isinstance(raw, dict) or depth > 8:
        notes.append("a damaged node inside the template was skipped")
        return None
    name = raw.get("name")
    kind = raw.get("kind", "function")
    if not isinstance(name, str) or not name.strip() or kind not in KINDS:
        notes.append("a damaged node inside the template was skipped")
        return None
    node = {"name": name.strip(), "kind": kind}
    if kind == "function":
        node["blocks"] = _blocks_from_json(raw.get("blocks"), notes)
    else:
        kids = raw.get("child_nodes")
        node["child_nodes"] = [c for c in (_parse_node(k, notes, depth + 1)
                                           for k in (kids if isinstance(kids, list) else [])) if c]
    return node


def parse_template(data):
    """-> (template or None, notes). Never raises; a bad file is just
    reported and ignored."""
    notes = []
    if not isinstance(data, dict):
        return None, ["not a node template"]
    if "format" in data and data["format"] != FORMAT:
        return None, ["not a node template"]
    top = _parse_node(data, notes)
    if top is None:
        return None, notes or ["not a node template"]
    variables, seen = [], set()
    raw_vars = data.get("variables")
    for v in raw_vars if isinstance(raw_vars, list) else []:
        if isinstance(v, str):
            v = {"name": v}
        if not isinstance(v, dict):
            continue
        n = v.get("name")
        if not isinstance(n, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) or n in seen:
            continue
        seen.add(n)
        label = v.get("label") if isinstance(v.get("label"), str) and v.get("label").strip() else n
        default = v.get("default")
        variables.append({"name": n, "label": label,
                          "default": default if isinstance(default, str) else ""})
        if len(variables) >= MAX_VARIABLES:
            break
    desc = data.get("description")
    top.update({"description": desc if isinstance(desc, str) else "", "variables": variables})
    return top, notes


# ------------------------------------------------------------------ folders

def safe_scope(scope):
    return isinstance(scope, str) and bool(_SAFE_SCOPE.match(scope))


def load_folder(root, language):
    """Entries for `language` + general under one root.
    -> (entries, notes); entry = {template, folder_kind, scope, path}."""
    entries, notes = [], []
    if not safe_scope(language):
        return entries, notes
    for scope in (GENERAL, language):
        for folder_kind in FOLDER_KINDS:
            folder = os.path.join(root, scope, folder_kind)
            if not os.path.isdir(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.lower().endswith(".json") or fname.startswith("."):
                    continue
                path = os.path.join(folder, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, ValueError) as e:
                    notes.append(f"{fname}: could not be read ({e.__class__.__name__})")
                    continue
                t, n = parse_template(data)
                if t is None:
                    notes.append(f"{fname}: {n[0] if n else 'not a node template'}")
                    continue
                notes += [f"{fname}: {x}" for x in n]
                entries.append({"template": t, "folder_kind": folder_kind,
                                "scope": scope, "path": path})
    entries.sort(key=lambda e: (e["template"]["name"].lower(), e["path"]))
    return entries, notes


def load_all(roots, language):
    """Entries from every distinct root (same real folder only once)."""
    entries, notes, seen = [], [], set()
    for root in roots:
        real = os.path.realpath(root)
        if real in seen:
            continue
        seen.add(real)
        e, n = load_folder(root, language)
        entries += e
        notes += n
    return entries, notes


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[:40] or "node"


def save_custom(root, scope, template):
    """Write a template into <root>/<scope>/custom/ without ever
    overwriting an existing file. Returns the path."""
    if not safe_scope(scope):
        raise ValueError(f"bad scope: {scope!r}")
    folder = os.path.join(root, scope, "custom")
    os.makedirs(folder, exist_ok=True)
    base = _slug(template["name"])
    path, n = os.path.join(folder, base + ".json"), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}_{n}.json")
        n += 1
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    os.replace(tmp, path)
    return path


# -------------------------------------------------------------- instantiate

def instantiate(template, values, known_block_ids, raw_block_id, raw_param, new_id):
    """Turn a parsed template into a fresh node tree. -> (node, notes).

    values: {variable: text}; a missing one falls back to its default.
    known_block_ids: blocks that exist in the current language; others are
    skipped with a note. new_id(): returns a fresh node id each call."""
    notes = []
    vals = {v["name"]: v["default"] for v in template.get("variables", [])}
    vals.update({k: v for k, v in (values or {}).items() if k in vals})

    def blocks_out(items):
        out = []
        for block_id, params in items:
            params = copy.deepcopy(params)
            children = params.pop("_children", None)
            params = _substitute(params, vals)
            if block_id == RAW_PSEUDO_BLOCK:
                if not raw_block_id:
                    notes.append("this language has no raw code block; a raw part was skipped")
                    continue
                text = params.get("code", "") if isinstance(params.get("code", ""), str) else ""
                if text.endswith("\n"):
                    text = text[:-1]
                for line in text.split("\n"):
                    out.append((raw_block_id, {raw_param: line}))
                continue
            if block_id not in known_block_ids:
                notes.append(f"block '{block_id}' is not available in this language and was skipped")
                continue
            if isinstance(children, list):
                params["_children"] = blocks_out(children)
            out.append((block_id, params))
        return out

    def build(t):
        name = _substitute(t["name"], vals)
        if t["kind"] == "class":
            return make_node(name, node_id=new_id(), kind="class",
                             child_nodes=[build(c) for c in t.get("child_nodes", [])])
        return make_node(name, node_id=new_id(), blocks=blocks_out(t.get("blocks", [])))

    return build(template), notes
