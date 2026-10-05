"""Portable Blockliner file format (pure, no Tk).

A portable file is ordinary source code plus comment lines that let another
Blockliner rebuild the project:

    # $$$blockliner:node:<id>$$$ start      one pair per function node,
    ...that node's code...                   written in execution order
    # $$$blockliner:node:<id>$$$ end

    # $$$blockliner:meta$$$                 optional, one block at the very
    # { ...JSON, one comment line each... } end of the file
    # $$$blockliner:meta:end$$$

Node markers carry ONLY the node id. Everything else portable (names, kinds,
nesting, canvas positions, ...) lives in the metadata block. The metadata is
optional: without it, nodes are rebuilt as a flat skeleton from the markers.

Only the literal tag text is ever matched, never the surrounding comment
characters, so parsing works whatever comment style a language uses. Nothing
in here raises on bad input - problems become diagnostics strings.
"""
import json
import re

from nodes_model import function_nodes_in_tree_order

META_VERSION = 1
META_START_TAG = "$$$blockliner:meta$$$"
META_END_TAG = "$$$blockliner:meta:end$$$"

# Node ids in the UI are strings ("main", short uuid hex, ...).
NODE_MARKER_RE = re.compile(r"\$\$\$blockliner:node:([A-Za-z0-9_\-]+)\$\$\$ (start|end)")

# Fallback canvas grid for nodes with no stored position (same spacing the
# Nodes layer uses). Temporary reconstruction heuristic, never authoritative.
GRID_START_X, GRID_START_Y = 30, 20
GRID_COL_WIDTH, GRID_ROW_HEIGHT, GRID_PER_ROW = 260, 150, 3


def grid_position(index):
    row, col = divmod(index, GRID_PER_ROW)
    return GRID_START_X + col * GRID_COL_WIDTH, GRID_START_Y + row * GRID_ROW_HEIGHT


def comment_line(token, text):
    """One comment line; `token` is "#", "//" or an [open, close] pair."""
    if isinstance(token, (list, tuple)) and len(token) == 2:
        return f"{token[0]} {text} {token[1]}"
    return f"{token if isinstance(token, str) else '#'} {text}"


def node_marker_lines(node_id, token):
    tag = f"$$$blockliner:node:{node_id}$$$"
    return comment_line(token, f"{tag} start"), comment_line(token, f"{tag} end")


# --- metadata --------------------------------------------------------------

def build_metadata(nodes, language, active_node_id=None):
    """Portable state for a node tree (list of UI node dicts, with
    child_nodes). Positions that are only loader fallbacks (`_auto_pos`
    still equal to the current position) are left out, so a fallback is
    never promoted to real layout data."""
    entries = {}
    # A node with no order key sits at its tree position (see
    # nodes_model.sorted_function_nodes), so write that as its order:
    # the file then reopens in exactly the same execution order.
    tree_rank = {id(n): i + 1 for i, n in enumerate(function_nodes_in_tree_order(nodes))}

    def walk(level, parent_id):
        for index, node in enumerate(level):
            entry = {
                "name": node.get("name"),
                "kind": node.get("kind", "function"),
                "parent": parent_id,
                "index": index,
            }
            for key in ("category", "locked", "node_type_id"):
                if node.get(key):
                    entry[key] = node[key]
            if "order" in node:
                entry["order"] = node["order"]
            elif id(node) in tree_rank:
                entry["order"] = tree_rank[id(node)]
            if "canvas_x" in node and "canvas_y" in node:
                pos = (node["canvas_x"], node["canvas_y"])
                if tuple(node.get("_auto_pos") or ()) != pos:
                    entry["x"], entry["y"] = pos
            entries[str(node["id"])] = entry
            walk(node.get("child_nodes") or [], node["id"])

    walk(nodes, None)
    meta = {"v": META_VERSION, "language": language, "nodes": entries}
    if active_node_id is not None:
        meta["active"] = active_node_id
    return meta


def render_meta_block(meta, token):
    """The metadata block as comment lines. '--' is escaped so the JSON
    can't end an HTML comment early."""
    body = json.dumps(meta, indent=1, sort_keys=True).replace("--", "-\\u002d")
    lines = [comment_line(token, META_START_TAG)]
    lines += [comment_line(token, ln) for ln in body.split("\n")]
    lines.append(comment_line(token, META_END_TAG))
    return "\n".join(lines) + "\n"


def _uncomment(line):
    s = line.strip()
    for opener in ("<!--", "//", "#"):
        if s.startswith(opener):
            s = s[len(opener):]
            break
    if s.endswith("-->"):
        s = s[:-3]
    return s[1:] if s.startswith(" ") else s


def _meta_span(lines):
    """(start_idx, end_idx) of the metadata block, or None. end_idx is
    None if the block was never closed."""
    start = next((i for i, ln in enumerate(lines) if META_START_TAG in ln), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if META_END_TAG in lines[i]), None)
    return start, end


def protected_line_numbers(lines):
    """1-based numbers of the lines safe mode protects: every node marker line
    and the whole metadata block (start tag to end tag; to the end if it was
    never closed)."""
    out = {i + 1 for i, ln in enumerate(lines) if NODE_MARKER_RE.search(ln)}
    span = _meta_span(lines)
    if span:
        start, end = span
        last = len(lines) - 1 if end is None else end
        out.update(range(start + 1, last + 2))
    return out


# --- building / stripping --------------------------------------------------

def assemble(head, chunks, tail, meta_block=""):
    """head + marker-wrapped chunks + tail (+ blank line + metadata).
    `chunks` is a list of (start_line, code, end_line); marker lines are
    indented to match `code`'s first line."""
    out = [head]
    for start_line, code, end_line, indent in chunks:
        out.append(f"{indent}{start_line}\n{code}{indent}{end_line}\n")
    out.append(tail)
    text = "".join(out)
    if meta_block:
        text += "\n" + meta_block
    return text


def strip_portable(text):
    """Text-only version: node marker lines and the metadata block removed,
    everything else byte-for-byte. Exact inverse of assemble() (the single
    blank separator before the metadata block goes with it)."""
    lines = text.splitlines(keepends=True)
    span = _meta_span(lines)
    if span:
        start, end = span
        cut_to = len(lines) if end is None else end + 1
        cut_from = start - 1 if start > 0 and lines[start - 1].strip() == "" else start
        lines = lines[:cut_from] + lines[cut_to:]
    return "".join(ln for ln in lines if not NODE_MARKER_RE.search(ln))


# --- parsing ---------------------------------------------------------------

def parse_portable(text, ignore_lines=()):
    """Returns (nodes, meta, diagnostics).
      nodes - [{"id", "code"}] in file order. `code` is the text between a
              node's start/end markers, as written (still indented).
      meta  - the metadata dict, or None if absent/unusable.
      diagnostics - human-readable notes; never fatal.
    Text outside any marker pair is not turned into nodes (it is wrapper
    boilerplate Blockliner regenerates); a note says how much was skipped,
    unless every such line is in `ignore_lines` (the expected wrapper)."""
    ignore_lines = set(ignore_lines)
    diagnostics = []
    lines = text.splitlines(keepends=True)

    meta = None
    span = _meta_span(lines)
    if span:
        start, end = span
        if end is None:
            diagnostics.append("metadata block was never closed - ignored")
        else:
            raw = "\n".join(_uncomment(ln.rstrip("\n")) for ln in lines[start + 1:end])
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and isinstance(parsed.get("nodes"), dict):
                    meta = parsed
                else:
                    diagnostics.append("metadata block has an unexpected shape - ignored")
            except ValueError as exc:
                diagnostics.append(f"metadata block is not valid JSON ({exc}) - ignored")
        cut_to = len(lines) if end is None else end + 1
        lines = lines[:start] + lines[cut_to:]

    nodes, node_lines, open_id, outside_chars = [], [], None, 0
    seen = set()

    def close(node_id):
        if node_id in seen:
            diagnostics.append(f"node '{node_id}' appears more than once - keeping the first")
        else:
            seen.add(node_id)
            nodes.append({"id": node_id, "code": "".join(node_lines)})

    for line in lines:
        m = NODE_MARKER_RE.search(line)
        if not m:
            if open_id is not None:
                node_lines.append(line)
            elif line.strip() and line.strip() not in ignore_lines:
                outside_chars += len(line)
            continue
        node_id, kind = m.group(1), m.group(2)
        if kind == "start":
            if open_id is not None:
                diagnostics.append(f"node '{node_id}' starts while '{open_id}' is still open - closing '{open_id}' early")
                close(open_id)
                node_lines = []
            open_id = node_id
        else:
            if open_id is None:
                diagnostics.append(f"node '{node_id}' end marker has no start - ignored")
                continue
            if open_id != node_id:
                diagnostics.append(f"node '{open_id}' start closed by '{node_id}' end - trusting the start id")
            close(open_id)
            node_lines, open_id = [], None
    if open_id is not None:
        diagnostics.append(f"node '{open_id}' was never closed - keeping its content")
        close(open_id)

    if outside_chars:
        diagnostics.append(f"{outside_chars} chars outside any node were skipped (wrapper code is regenerated)")
    return nodes, meta, diagnostics


def dedent_code(code, indent):
    """Remove one wrapper indent level (C++/C#/Java bodies) from each line
    that has it; other lines are untouched."""
    if not indent:
        return code
    return "".join(ln[len(indent):] if ln.startswith(indent) else ln for ln in code.splitlines(keepends=True))


def rebuild_nodes(text, language, wrapper_indent="", wrapper_text="", meta_override=None):
    """Turn a portable file's text into UI-shaped node descriptions.

    Returns (nodes, active_id, diagnostics). `nodes` is a list of plain
    dicts shaped like make_node's output, except each function node carries
    `code` (its de-indented source) in place of `blocks` - the UI turns that
    into blocks with its Code -> Blocks matcher.

    With metadata: nodes, kinds, nesting, order, state and saved positions
    come from it (markers supply each function node's code). Without it: a
    flat skeleton of function nodes, named after their id, ordered as they
    appear (file order IS execution order). Relationships (wires, parents)
    are never guessed. Nodes without a saved position get a grid slot,
    flagged in `_auto_pos` so it isn't saved back as real layout.
    """
    marked, meta, diagnostics = parse_portable(
        text, ignore_lines={ln.strip() for ln in wrapper_text.splitlines()})
    if meta is None and meta_override is not None:
        meta = meta_override  # sidecar data; a valid block inside the file wins
    code_by_id = {n["id"]: dedent_code(n["code"], wrapper_indent) for n in marked}
    file_order = [n["id"] for n in marked]
    active = None

    entries = meta["nodes"] if meta else {}
    if meta:
        if meta.get("language") not in (None, language):
            diagnostics.append(f"metadata says language '{meta.get('language')}', file loaded as '{language}'")
        active = meta.get("active")

    flat = {}

    def new_node(node_id, entry):
        entry = entry if isinstance(entry, dict) else {}
        kind = entry.get("kind", "function")
        node = {
            "id": node_id, "name": entry.get("name") or node_id,
            "category": entry.get("category"), "kind": kind,
            "blocks": [], "child_nodes": [],
            "locked": bool(entry.get("locked", False)),
            "node_type_id": entry.get("node_type_id"), "references": [],
        }
        if kind == "function":
            node["code"] = code_by_id.get(node_id, "")
            if "order" in entry:
                node["order"] = entry["order"]
        if isinstance(entry.get("x"), (int, float)) and isinstance(entry.get("y"), (int, float)):
            node["canvas_x"], node["canvas_y"] = entry["x"], entry["y"]
        return node

    for node_id, entry in entries.items():
        flat[node_id] = new_node(node_id, entry)
        if flat[node_id]["kind"] == "function" and node_id not in code_by_id:
            diagnostics.append(f"node '{node_id}' ({flat[node_id]['name']}) has no markers in the file - restored empty")

    # markers the metadata doesn't know about: flat extra function nodes
    for node_id in file_order:
        if node_id not in flat:
            if meta:
                diagnostics.append(f"node '{node_id}' is in the file but not in the metadata - added as a plain node")
            flat[node_id] = new_node(node_id, {})

    # nesting: only what the metadata states; an unknown/self/cyclic parent
    # means "unrecovered", so the node stays top-level
    def parent_of(node_id):
        entry = entries.get(node_id)
        return entry.get("parent") if isinstance(entry, dict) else None

    def acyclic_parent(node_id):
        parent = parent_of(node_id)
        seen = {node_id}
        while parent is not None:
            if parent not in flat or parent in seen or flat[parent]["kind"] == "function":
                return None
            seen.add(parent)
            parent = parent_of(parent)
        return parent_of(node_id)

    def sort_key(node_id):
        entry = entries.get(node_id)
        idx = entry.get("index") if isinstance(entry, dict) else None
        pos = file_order.index(node_id) if node_id in file_order else len(file_order)
        return (idx if isinstance(idx, int) else 10 ** 6, pos)

    top = []
    for node_id in sorted(flat, key=sort_key):
        parent = acyclic_parent(node_id)
        if parent is None:
            if parent_of(node_id) is not None:
                diagnostics.append(f"node '{node_id}' has an unusable parent - placed at the top level")
            top.append(flat[node_id])
        else:
            flat[parent]["child_nodes"].append(flat[node_id])

    # without metadata, file order is the order; with it, keep its numbers
    # and give any node lacking one the next free slot in file order
    fn_nodes = [flat[i] for i in file_order if i in flat and flat[i]["kind"] == "function"]
    taken = [n["order"] for n in flat.values() if isinstance(n.get("order"), int)]
    nxt = (max(taken) if taken else 0) + 1
    for n in fn_nodes:
        if "order" not in n:
            n["order"] = nxt
            nxt += 1

    # fallback grid for anything without a saved position (flat, deterministic)
    def place(level):
        for index, node in enumerate(level):
            if "canvas_x" not in node:
                node["canvas_x"], node["canvas_y"] = grid_position(index)
                node["_auto_pos"] = (node["canvas_x"], node["canvas_y"])
            place(node["child_nodes"])
    place(top)

    if active not in flat:
        active = next((n["id"] for n in fn_nodes), None)
    return top, active, diagnostics


# --- sidecar file (<code file>.blockliner.json) ------------------------------

SIDECAR_SUFFIX = ".blockliner.json"


def sidecar_path(code_path):
    return code_path + SIDECAR_SUFFIX


def render_sidecar(meta):
    return json.dumps(meta, indent=1, sort_keys=True) + "\n"


def parse_sidecar(text):
    """(meta, diagnostics). Strict: anything wrong -> meta None plus a note
    naming what was wrong, so the caller falls back to the markers."""
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        return None, [f"sidecar file is not valid JSON ({exc}) - ignored, rebuilt from markers"]
    if not isinstance(parsed, dict) or not isinstance(parsed.get("nodes"), dict):
        return None, ["sidecar file has an unexpected shape (no 'nodes' table) - ignored, rebuilt from markers"]
    bad = [k for k, v in parsed["nodes"].items() if not isinstance(v, dict)]
    if bad:
        return None, [f"sidecar entries for {', '.join(sorted(bad)[:5])} are not objects - ignored, rebuilt from markers"]
    return parsed, []


# --- files with no markers at all ------------------------------------------

_ID_BAD = re.compile(r"[^A-Za-z0-9_\-]")


def split_python_top_level(text):
    """Split plain Python into [(name, code)] by top-level def/class; runs of
    other top-level statements (imports, assignments, ...) become
    'top_level' chunks. Order is file order and nothing is dropped.
    Returns None if the text doesn't parse (caller keeps it as one node)."""
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    lines = text.splitlines(keepends=True)
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    spans = []  # (name or None, last line number)
    for stmt in tree.body:
        spans.append((stmt.name if isinstance(stmt, kinds) else None, stmt.end_lineno))
    chunks = []
    cursor = 0  # each chunk starts where the previous ended, so decorators/comments stay attached
    for name, end in spans:
        if name is None:
            if chunks and chunks[-1][0] is None:
                chunks[-1][2] = end
            else:
                chunks.append([None, cursor, end])
        else:
            chunks.append([name, cursor, end])
        cursor = end
    if chunks:
        chunks[-1][2] = len(lines)  # trailing blank/comment lines stay attached
    return [(n or "top_level", "".join(lines[a:b])) for n, a, b in chunks]


def wrap_with_markers(chunks, token="#"):
    """[(name, code)] -> marker-wrapped text with unique safe ids."""
    used, out = set(), []
    for name, code in chunks:
        base = _ID_BAD.sub("_", name) or "node"
        node_id, n = base, 2
        while node_id in used:
            node_id, n = f"{base}_{n}", n + 1
        used.add(node_id)
        start, end = node_marker_lines(node_id, token)
        if code and not code.endswith("\n"):
            code += "\n"
        out.append(f"{start}\n{code}{end}\n")
    return "".join(out)
