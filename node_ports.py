"""Node ports (ComfyUI style). Pure module (no Tk).

A node is not a function, but a node that holds a "Define Function" block
named like the node has an interface: that function's parameters are the
node's INPUT ports and the values it returns are its OUTPUT ports.
Nothing here changes generated code - ports are derived from the blocks,
never hand-authored. Only the colours can be set by hand
(node["port_colors"] = {"out:user": "#rrggbb", ...}); everything else is
recomputed every time.
"""
import re
import zlib

PORT_COLORS = [
    ("Blue", "#4f8fd6"), ("Green", "#4fbf7a"), ("Orange", "#e0953f"),
    ("Red", "#d65a5a"), ("Purple", "#a070d0"), ("Cyan", "#3fc4d6"),
    ("Pink", "#d670b0"), ("Yellow", "#d6c84f"),
]
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


def node_interface(node):
    """(inputs, outputs): names only. Both empty unless the node holds a
    func_def named like itself."""
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
    return [], []


def auto_color(name, taken=()):
    """Same name -> same colour (so an output 'user' and an input 'user'
    match); ports of one side that would collide get the next free colour."""
    start = zlib.crc32(name.encode("utf-8")) % len(PORT_COLORS)
    for step in range(len(PORT_COLORS)):
        col = PORT_COLORS[(start + step) % len(PORT_COLORS)][1]
        if col not in taken:
            return col
    return PORT_COLORS[start][1]


def valid_color(value):
    return isinstance(value, str) and bool(_HEX.match(value))


def node_ports(node):
    """[{"side": "in"|"out", "name", "color", "manual": bool}] - inputs first."""
    inputs, outputs = node_interface(node)
    overrides = node.get("port_colors") if isinstance(node.get("port_colors"), dict) else {}
    ports = []
    for side, names in (("in", inputs), ("out", outputs)):
        taken = {overrides[f"{side}:{n}"] for n in names
                 if valid_color(overrides.get(f"{side}:{n}"))}
        for n in names:
            manual = overrides.get(f"{side}:{n}")
            if valid_color(manual):
                color, is_manual = manual, True
            else:
                color, is_manual = auto_color(n, taken), False
                taken.add(color)
            ports.append({"side": side, "name": n, "color": color, "manual": is_manual})
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
