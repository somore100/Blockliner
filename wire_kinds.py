"""Wire kinds and how they look. Pure module (no Tk).

Every wire is DERIVED from the code, never stored; its kind is derived too:
  call   - a plain call block ("verify(x)"): the caller just runs the callee.
  data   - the callee's RESULT is used ("ok = verify(x)"), or the wire carries
           a variable one node assigns and a later node reads.
  import - a file imports another file (Files layer).
One style table, so the canvas, the tests and any future legend agree.
"""

KINDS = ("call", "data", "import")

# colour, dash pattern (None = solid), line width
STYLES = {
    "call":   {"color": "#6a9955", "dash": None,   "width": 2},
    "data":   {"color": "#4f8fd6", "dash": (6, 4), "width": 2},
    "import": {"color": "#b57edc", "dash": (2, 5), "width": 2},
}
SELECTED_COLOR = "#e8a33d"      # a clicked call wire (any kind keeps its dash)
SELECTED_WIDTH = 3


def style_for(kind, selected=False):
    """{"color", "dash", "width"} for a kind; unknown kinds look like calls."""
    base = STYLES.get(kind) or STYLES["call"]
    if selected:
        return {"color": SELECTED_COLOR, "dash": base["dash"], "width": SELECTED_WIDTH}
    return dict(base)


def _chip_names(value, out):
    """Names of every call chip held (at any depth) in a param value."""
    if isinstance(value, dict):
        if value.get("_nested_block") == "func_call":
            p = value.get("_nested_params")
            if isinstance(p, dict):
                name = str(p.get("name") or "").strip()
                if name:
                    out.add(name)
        for k, v in value.items():
            if k != "_nested_block":
                _chip_names(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _chip_names(v, out)


def call_kinds(blocks):
    """{called name: "call" | "data"} for every call in a block list (children
    and chips included). A name is "data" as soon as ONE use takes its result
    (a call chip inside another block, e.g. "ok = verify(x)"); otherwise a
    plain call block makes it "call"."""
    plain, chips = set(), set()

    def walk(entries):
        for entry in entries or []:
            try:
                bid, params = entry
            except (TypeError, ValueError):
                continue
            if not isinstance(params, dict):
                continue
            if bid == "func_call":
                name = str(params.get("name") or "").strip()
                if name:
                    plain.add(name)
            for k, v in params.items():
                if k == "_children":
                    if isinstance(v, list):
                        walk(v)
                else:
                    _chip_names(v, chips)

    walk(blocks)
    return {name: ("data" if name in chips else "call") for name in plain | chips}
