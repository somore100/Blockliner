"""Node ports (ComfyUI style). Pure module (no Tk).

A CATEGORY has OUTPUT ports too: every output port of the nodes inside it
(any depth) that no other node inside it uses (see category_ports).

A node is not a function, but a node that holds a "Define Function" block
named like the node has an interface: that function's parameters are the
node's INPUT ports and the values it returns are its OUTPUT ports.
A node WITHOUT such a function has no inputs, and its OUTPUT ports are the
variables its top-level code assigns ("text = make_password()" -> port "text").
Nothing here changes generated code - ports are derived from the blocks,
never hand-authored. Only the colours can be set by hand
(node["port_colors"] = {"out:user": "#rrggbb", ...}); everything else is
recomputed every time.
"""
import keyword
import re
import zlib

PORT_COLORS = [
    ("Blue", "#4f8fd6"), ("Green", "#4fbf7a"), ("Orange", "#e0953f"),
    ("Red", "#d65a5a"), ("Purple", "#a070d0"), ("Cyan", "#3fc4d6"),
    ("Pink", "#d670b0"), ("Yellow", "#d6c84f"),
]
# Port colour = MEANING when the type is known for certain (annotation or a
# literal assignment), otherwise a stable colour from the name. The type
# colours are never used for untyped ports (while a side has <= 3 of them).
TYPE_COLORS = {
    "text": "#4f8fd6",      # blue
    "number": "#e0953f",    # orange
    "bool": "#d65a5a",      # red
    "list": "#a070d0",      # purple
    "dict": "#3fc4d6",      # cyan
}
TYPE_LABELS = {"text": "text", "number": "number", "bool": "true/false",
               "list": "list", "dict": "map"}
_NEUTRAL_COLORS = ["#4fbf7a", "#d670b0", "#d6c84f"]     # green, pink, yellow
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_SKIP_PARAMS = {"self", "cls"}
MAX_NAME = 24


def split_commas(text):
    """Split on commas that are not inside (), [], {} or quotes."""
    parts, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def param_names(text):
    """'a, b=1, *args, c: int, int d' -> ['a', 'b', 'args', 'c', 'd']."""
    names = []
    for piece in split_commas(text or ""):
        piece = piece.split("=", 1)[0]            # drop a default value
        if ":" in piece:                          # drop a Python annotation
            piece = piece.split(":", 1)[0]
        idents = _IDENT.findall(piece)
        if idents and idents[-1] not in _SKIP_PARAMS and idents[-1] not in names:
            names.append(idents[-1])
    return names


def return_names(expr):
    """'user, error' -> ['user', 'error']; '(a, b)' -> ['a', 'b']; '' -> []."""
    expr = (expr or "").strip()
    if len(expr) >= 2 and expr[0] in "([" and expr[-1] in ")]" and \
            len(split_commas(expr[1:-1])) > 1:
        expr = expr[1:-1]
    return [_short(p) for p in split_commas(expr)]


def _short(name):
    name = " ".join(name.split())
    return name if len(name) <= MAX_NAME else name[:MAX_NAME - 1] + "…"


def _walk(blocks):
    """Every (block_id, params) in a block list, children included, in order."""
    for entry in blocks or []:
        try:
            block_id, params = entry
        except (TypeError, ValueError):
            continue
        yield block_id, params
        kids = params.get("_children") if isinstance(params, dict) else None
        if isinstance(kids, list):
            yield from _walk(kids)


_STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
_NAME = re.compile(r"(?<![\w.])[A-Za-z_]\w*")
_STRING_ONLY = re.compile(r"^(?:[rbfRBF]{0,2})(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')$")
_NUMBER_LIT = re.compile(r"^-?(?:\d[\d_]*\.?\d*(?:[eE][-+]?\d+)?|\.\d+)$")
_NOT_CODE_KEYS = {"name", "params", "variable", "_children", "_nested_block"}


def idents(text):
    """Bare identifiers in a piece of code: string literals and attribute
    names (obj.x) are ignored."""
    return _NAME.findall(_STRING.sub('""', text or ""))


def _value_idents(value):
    if isinstance(value, str):
        return idents(value)
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            if k not in _NOT_CODE_KEYS:
                out += _value_idents(v)
        return out
    if isinstance(value, (list, tuple)):
        return [i for v in value for i in _value_idents(v)]
    return []


def has_function(node):
    """True when the node holds a func_def named like itself."""
    name = (node.get("name") or "").strip()
    return any(bid == "func_def" and isinstance(p, dict) and str(p.get("name") or "").strip() == name
               for bid, p in _walk(node.get("blocks")))


def assigned_names(node):
    """Variables assigned by the node's TOP-LEVEL assign blocks, in order."""
    out = []
    for entry in node.get("blocks") or []:
        try:
            bid, p = entry
        except (TypeError, ValueError):
            continue
        if bid != "assign_variable" or not isinstance(p, dict) or not isinstance(p.get("variable"), str):
            continue
        for n in return_names(p["variable"]):
            if n.isidentifier() and not keyword.iskeyword(n) and n not in out:
                out.append(n)
    return out


def node_interface(node):
    """(inputs, outputs): names only. With a func_def named like the node:
    its parameters and returned values. Without one: no inputs, and the
    variables the node assigns at its top level as outputs."""
    if node.get("kind", "function") != "function":
        return [], []
    name = (node.get("name") or "").strip()
    for block_id, params in _walk(node.get("blocks")):
        if block_id != "func_def" or not isinstance(params, dict):
            continue
        if str(params.get("name") or "").strip() != name:
            continue
        inputs = param_names(params.get("params") if isinstance(params.get("params"), str) else "")
        outputs = []
        for bid, p in _walk(params.get("_children")):
            if bid == "return_statement" and isinstance(p, dict) and isinstance(p.get("value"), str):
                for n in return_names(p["value"]):
                    if n not in outputs:
                        outputs.append(n)
        return inputs, outputs
    return [], assigned_names(node)


_QUALIFIERS = {"const", "mut", "unsigned", "signed", "std", "final", "ref", "var", "let",
               "readonly", "volatile", "static", "struct", "long long"}
_TEXT = {"str", "string", "char", "text", "wstring", "cstring", "rune", "varchar",
         "cstr", "stringbuilder", "charsequence"}
_BOOL = {"bool", "boolean"}
_LIST = {"list", "vec", "array", "arraylist", "slice", "tuple", "set", "vector",
         "deque", "sequence", "iterable", "hashset", "linkedlist"}
_DICT = {"dict", "map", "hashmap", "mapping", "record", "treemap", "dictionary", "btreemap"}
_NUMBER = {"int", "integer", "long", "short", "float", "double", "number", "decimal", "byte",
           "usize", "isize", "size_t", "bigint", "complex", "f32", "f64", "float32", "float64",
           "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64",
           "i8", "i16", "i32", "i64", "i128", "u8", "u16", "u32", "u64", "u128", "single"}
_WRAPPERS = {"optional", "option", "nullable", "final", "readonly", "box"}


def classify_type(text):
    """Type text from a signature -> "text" | "number" | "bool" | "list" | "dict"
    | None (unknown: never guessed). 'str', 'int', '&str', 'List[int]',
    'Vec<i32>', 'char *', 'String[]', 'Optional[str]' ..."""
    t = (text or "").strip()
    if not t:
        return None
    if t.endswith("[]") or t.startswith("["):
        return "list"
    words = [w.lower() for w in re.findall(r"[A-Za-z_]\w*", t)]
    words = [w for w in words if w not in _QUALIFIERS]
    if not words:
        return None
    base = words[0]
    if base in _WRAPPERS and len(words) > 1:
        base = words[1]
    if base == "char" and "*" in t:
        return "text"
    for kind, names in (("text", _TEXT), ("bool", _BOOL), ("list", _LIST),
                        ("dict", _DICT), ("number", _NUMBER)):
        if base in names:
            return kind
    return None


def param_types(text):
    """{param name: kind} for the parameters whose type is written in the
    signature: 'a: int, b, String c, const char *d=0' -> a number, c text, d text."""
    out = {}
    for piece in split_commas(text or ""):
        piece = piece.split("=", 1)[0]
        if ":" in piece:
            name_part, type_part = piece.split(":", 1)
            found = _IDENT.findall(name_part)
            name = found[-1] if found else None
        else:
            found = list(_IDENT.finditer(piece))
            if len(found) < 2:
                continue
            name, type_part = found[-1].group(0), piece[:found[-1].start()]
        kind = classify_type(type_part)
        if name and name not in _SKIP_PARAMS and kind:
            out.setdefault(name, kind)
    return out


def literal_type(expr):
    """Kind of a literal value ('"hi"' text, '3.5' number, 'True' bool, '[1]' list,
    '{}' dict); None for anything that is not a plain literal."""
    e = (expr or "").strip()
    if not e:
        return None
    if _STRING_ONLY.match(e):
        return "text"
    if _NUMBER_LIT.match(e):
        return "number"
    if e in ("True", "False", "true", "false"):
        return "bool"
    if e[0] in "[{" and _one_bracket_group(e):
        if e[0] == "[":
            return "list"
        return "dict" if e == "{}" or ":" in "".join(split_commas(e[1:-1])[:1]) else "list"
    return None


def _one_bracket_group(e):
    """True when e is ONE bracket pair from first to last char ('[1,2]', not '[a][0]')."""
    depth, quote = 0, None
    for i, ch in enumerate(e):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0 and i != len(e) - 1:
                return False
    return depth == 0 and e[-1] in ")]}"


def node_types(node):
    """{"in:name": kind, "out:name": kind} - only what is certain: a typed
    parameter of the node's function, and a variable assigned a literal."""
    types = {}
    if has_function(node):
        name = (node.get("name") or "").strip()
        for bid, p in _walk(node.get("blocks")):
            if bid == "func_def" and isinstance(p, dict) and str(p.get("name") or "").strip() == name:
                if isinstance(p.get("params"), str):
                    for n, k in param_types(p["params"]).items():
                        types[f"in:{n}"] = k
                break
        return types
    for entry in node.get("blocks") or []:
        try:
            bid, p = entry
        except (TypeError, ValueError):
            continue
        if bid == "assign_variable" and isinstance(p, dict) and isinstance(p.get("variable"), str):
            names = [n for n in return_names(p["variable"]) if n.isidentifier()]
            kind = literal_type(p.get("value")) if isinstance(p.get("value"), str) else None
            for n in names:
                if kind and len(names) == 1:
                    types[f"out:{n}"] = kind
                else:
                    types.pop(f"out:{n}", None)       # reassigned to something unknown
    return types


def auto_color(name, taken=()):
    """Same name -> same colour (so an output 'user' and an input 'user'
    match). Uses the neutral colours first (the type colours mean something),
    then the rest; ports of one side that would collide get the next free one."""
    order = _NEUTRAL_COLORS + [c for _n, c in PORT_COLORS if c not in _NEUTRAL_COLORS]
    start = zlib.crc32(name.encode("utf-8")) % len(_NEUTRAL_COLORS)
    ring = order[start:len(_NEUTRAL_COLORS)] + order[:start] + order[len(_NEUTRAL_COLORS):]
    for col in ring:
        if col not in taken:
            return col
    return ring[0]


def valid_color(value):
    return isinstance(value, str) and bool(_HEX.match(value))


def node_ports(node):
    """[{"side": "in"|"out", "name", "color", "manual": bool}] - inputs first."""
    inputs, outputs = node_interface(node)
    overrides = node.get("port_colors") if isinstance(node.get("port_colors"), dict) else {}
    types = node_types(node)
    ports = []
    for side, names in (("in", inputs), ("out", outputs)):
        taken = {overrides[f"{side}:{n}"] for n in names
                 if valid_color(overrides.get(f"{side}:{n}"))}
        for n in names:
            manual = overrides.get(f"{side}:{n}")
            if valid_color(manual):
                color, is_manual = manual, True
            elif f"{side}:{n}" in types:
                color, is_manual = TYPE_COLORS[types[f"{side}:{n}"]], False
            else:
                color, is_manual = auto_color(n, taken), False
                taken.add(color)
            ports.append({"side": side, "name": n, "color": color, "manual": is_manual,
                          "type": types.get(f"{side}:{n}")})
    return ports


def set_port_color(node, side, name, color):
    """Manual colour for one port; color None / invalid = back to automatic."""
    key = f"{side}:{name}"
    colors = node.setdefault("port_colors", {})
    if valid_color(color):
        colors[key] = color
    else:
        colors.pop(key, None)
    if not colors:
        node.pop("port_colors", None)


def clean_port_colors(raw):
    """Loader guard: keep only well-formed 'in:x'/'out:x' -> '#rrggbb' pairs."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items()
            if isinstance(k, str) and (k.startswith("in:") or k.startswith("out:"))
            and valid_color(v)}


def data_wires(ordered_nodes):
    """Derived DATA wires between function nodes. `ordered_nodes` = the live
    nodes (not ignored/skipped) in run order. A node that assigns a variable
    at its top level and has no function of its own PRODUCES it; a later node
    whose code reads that name (and has not assigned/declared it itself first)
    USES it. The producer is the nearest earlier node that assigns the name.
    Returns [(producer_id, user_id, [names])], one entry per pair, in run
    order. Nothing is stored - recomputed from the blocks every time."""
    latest = {}                         # variable -> producing node
    found = {}                          # (producer id, user id) -> [names]
    pairs = []
    for node in ordered_nodes:
        if node.get("kind", "function") != "function":
            continue
        local = set(node_interface(node)[0])          # its own parameters
        for _bid, params in _walk(node.get("blocks")):
            if not isinstance(params, dict):
                continue
            for key, value in params.items():
                if key in _NOT_CODE_KEYS:
                    continue
                for name in _value_idents(value):
                    prod = latest.get(name)
                    if name in local or prod is None:
                        continue
                    key2 = (prod["id"], node["id"])
                    if key2 not in found:
                        found[key2] = []
                        pairs.append(key2)
                    if name not in found[key2]:
                        found[key2].append(name)
            var = params.get("variable")
            if isinstance(var, str):
                local.update(idents(var))
        if not has_function(node):
            for name in assigned_names(node):
                latest[name] = node
    return [(a, b, found[(a, b)]) for a, b in pairs]


def _live_functions(nodes):
    """Function nodes (any depth) that take part in the generated code."""
    out = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        if n.get("kind", "function") == "function":
            if not n.get("ignored") and not n.get("skipped"):
                out.append(n)
        out.extend(_live_functions(n.get("child_nodes")))
    return out


def category_ports(category):
    """OUTPUT ports of a category: each output port of a node inside it that
    NO OTHER node inside it uses. A function node's outputs count as used when
    another inner node calls it (node["references"]); a variable port counts as
    used when another inner node reads it (node["data_uses"]). Uses from
    outside the category do not hide a port. Ignored/skipped nodes take no part.
    [{"side": "out", "name", "label", "color", "manual", "src": inner node id}]
    - `label` gets the node name in front only when two ports share a name."""
    if not isinstance(category, dict) or category.get("kind") != "category":
        return []
    inner = _live_functions(category.get("child_nodes"))
    called = set()
    read = set()
    for n in inner:
        for ref in n.get("references") or []:
            if ref != n.get("id"):
                called.add(ref)
        for use in n.get("data_uses") or []:
            if isinstance(use, dict) and use.get("id") != n.get("id"):
                for v in use.get("vars") or []:
                    read.add((use.get("id"), v))
    ports = []
    for n in inner:
        function = has_function(n)
        for p in node_ports(n):
            if p["side"] != "out":
                continue
            used = n.get("id") in called if function else (n.get("id"), p["name"]) in read
            if not used:
                ports.append(dict(p, src=n.get("id"), node=n.get("name") or n.get("id")))
    counts = {}
    for p in ports:
        counts[p["name"]] = counts.get(p["name"], 0) + 1
    for p in ports:
        p["label"] = f"{p.pop('node')}.{p['name']}" if counts[p["name"]] > 1 else p["name"]
    return ports
