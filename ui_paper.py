"""Paper preview for the UI designer (pure, no Tk): where each widget of a
UITree is drawn on the design surface. A rough layouter, not the real toolkit:
grid children get rows/columns sized by their contents, place children go at
their x/y, anything else is stacked. Real widgets are never created here, so
it works for any pack. The Tk side is in ui_designer.py."""

# key -> (label, paper width, paper height)
DEVICES = {
    "desktop": ("Computer", 560, 380),
    "phone": ("Phone", 240, 440),
    "tablet": ("Tablet", 400, 520),
}
DEFAULT_DEVICE = "desktop"
GAP = 6                 # space between stacked children
PAD = 8                 # inside a container


DEFAULT_FONT = ("Helvetica", 9)
FONT_STYLES = ("bold", "italic", "underline", "overstrike")


def parse_font(value):
    """(family, size, [styles]) from a Tk font value: "Arial 12 bold",
    "{Segoe UI} 12", ("Arial", 12, "bold") or None (the default font)."""
    if isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    elif isinstance(value, str) and value.strip():
        parts, buf, depth = [], "", 0
        for ch in value.strip():
            if ch == "{":
                depth += 1
                if depth == 1:
                    continue
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    parts.append(buf); buf = ""
                    continue
            if ch.isspace() and depth == 0:
                if buf:
                    parts.append(buf); buf = ""
                continue
            buf += ch
        if buf:
            parts.append(buf)
    else:
        return DEFAULT_FONT[0], DEFAULT_FONT[1], []
    family = parts[0] if parts else DEFAULT_FONT[0]
    size, styles = DEFAULT_FONT[1], []
    for p in parts[1:]:
        if p.lstrip("-").isdigit():
            size = abs(int(p)) or DEFAULT_FONT[1]
        elif p in FONT_STYLES and p not in styles:
            styles.append(p)
    return family, size, styles


def format_font(family, size, styles=()):
    """The Tk font string for parse_font's parts ("{Segoe UI} 12 bold")."""
    family = (family or DEFAULT_FONT[0]).strip()
    fam = "{" + family + "}" if any(c.isspace() for c in family) else family
    return " ".join([fam, str(int(size))] + [s for s in FONT_STYLES if s in styles])


def device_size(device):
    _label, w, h = DEVICES.get(device) or DEVICES[DEFAULT_DEVICE]
    return w, h


def _num(value, fallback=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else fallback


def natural_size(node, wdef):
    """(w, h) a leaf widget would take, from its text / width prop / default size."""
    w, h = (wdef["default_size"] if wdef else None) or (80, 24)
    props = node["props"]
    size = parse_font(props.get("font"))[1]
    k = size / DEFAULT_FONT[1]                  # bigger text, bigger widget
    cw, lh = 7 * k, 16 * k
    h = max(h, round(lh + 8))
    text = props.get("text")
    if isinstance(text, str) and text:
        w = max(w if node["type"] != "label" else 0, round(cw * len(text) + 20))
    if isinstance(props.get("width"), int) and props["width"] > 0:
        w = round(cw * props["width"] + 10)
    if isinstance(props.get("height"), int) and props["height"] > 0 and node["type"] in ("text", "listbox"):
        h = round(lh * props["height"] + 8)
    return w, h


def _kids(node):
    return [c for c in node["children"] if isinstance(c, dict)]


def _groups(node):
    grid, place, stack = [], [], []
    for c in _kids(node):
        lay = c["layout"]
        manager = lay.get("manager")
        if manager == "grid" or (manager is None and ("row" in lay or "column" in lay)):
            grid.append(c)
        elif manager == "place" or (manager is None and ("x" in lay or "y" in lay)):
            place.append(c)
        else:
            stack.append(c)
    return grid, place, stack


class Paper:
    def __init__(self, tree, pack):
        self.tree, self.pack = tree, pack
        self._size = {}
        self.tracks = {}       # container id -> (col x, col widths, row y, row heights), relative

    def measure(self, node):
        key = node["id"]
        if key in self._size:
            return self._size[key]
        wdef = self.pack.widget(node["type"])
        if node["children"]:
            rel, cw, ch = self._arrange(node)
            base = natural_size(node, wdef)
            size = (max(base[0] if node["id"] != self.tree.root["id"] else 0, cw + PAD),
                    max(base[1] if node["id"] != self.tree.root["id"] else 0, ch + PAD))
        else:
            size = natural_size(node, wdef)
        self._size[key] = size
        return size

    def _arrange(self, node):
        """({child id: (dx, dy, w, h)}, content width, content height)."""
        grid, place, stack = _groups(node)
        rel, right, bottom = {}, 0, 0
        if grid:
            cols, rows = {}, {}
            for c in grid:
                lay, (w, h) = c["layout"], self.measure(c)
                w += 2 * _num(lay.get("padx")); h += 2 * _num(lay.get("pady"))
                if _num(lay.get("columnspan"), 1) <= 1:
                    cols[_num(lay.get("column"))] = max(cols.get(_num(lay.get("column")), 0), w)
                if _num(lay.get("rowspan"), 1) <= 1:
                    rows[_num(lay.get("row"))] = max(rows.get(_num(lay.get("row")), 0), h)
            xs, ys, x, y = {}, {}, PAD, PAD
            for k in sorted(cols):
                xs[k] = x; x += cols[k]
            for k in sorted(rows):
                ys[k] = y; y += rows[k]
            self.tracks[node["id"]] = (xs, cols, ys, rows)
            for c in grid:
                lay, (w, h) = c["layout"], self.measure(c)
                col, row = _num(lay.get("column")), _num(lay.get("row"))
                cx = xs.get(col, PAD) + _num(lay.get("padx"))
                cy = ys.get(row, PAD) + _num(lay.get("pady"))
                rel[c["id"]] = (cx, cy, w, h)
                right, bottom = max(right, cx + w), max(bottom, cy + h)
        for c in place:
            lay, (w, h) = c["layout"], self.measure(c)
            w, h = _num(lay.get("width"), w), _num(lay.get("height"), h)
            rel[c["id"]] = (_num(lay.get("x")), _num(lay.get("y")), w, h)
            right, bottom = max(right, _num(lay.get("x")) + w), max(bottom, _num(lay.get("y")) + h)
        y = bottom + GAP if bottom else PAD
        for c in stack:
            w, h = self.measure(c)
            rel[c["id"]] = (PAD, y, w, h)
            right, bottom, y = max(right, PAD + w), y + h, y + h + GAP
        return rel, right, bottom

    def boxes(self, paper_w, paper_h):
        """[{id, type, x, y, w, h, depth}] parent-first, so later = on top."""
        out = []
        root = self.tree.root

        def walk(node, x, y, w, h, depth):
            out.append({"id": node["id"], "type": node["type"], "x": x, "y": y, "w": w, "h": h, "depth": depth})
            if node["children"]:
                rel, _cw, _ch = self._arrange(node)
                for c in _kids(node):
                    dx, dy, cw, ch = rel[c["id"]]
                    walk(c, x + dx, y + dy, cw, ch, depth + 1)
        walk(root, 0, 0, paper_w, paper_h, 0)
        return out


def hit_test(boxes, x, y):
    """Id of the topmost (deepest, latest) box containing the point, or None."""
    for b in reversed(boxes):
        if b["x"] <= x <= b["x"] + b["w"] and b["y"] <= y <= b["y"] + b["h"]:
            return b["id"]
    return None
