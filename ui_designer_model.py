"""Pure helpers for the UI designer view (no Tk): where a new widget goes, what
layout it starts with, turning typed text into property values, outline rows.
The Tk side is in ui_designer.py."""

import ui_paper

FIELD_KINDS_TEXT = ("string", "color", "font", "code")
HANDLE = 6              # px (on screen) around an edge that grabs it for resizing
MIN_SIZE = 10


def add_target(tree, pack, selected_id):
    """Parent id a new widget goes under: the selected widget if it can hold
    children, else the selected widget's parent, else the root."""
    sel = tree.find(selected_id) if selected_id else None
    if sel is not None:
        if pack.is_container(sel["type"]):
            return sel["id"]
        parent = tree.parent_of(sel["id"])
        if parent is not None:
            return parent["id"]
    return tree.root["id"]


PREFERRED_MANAGER = "place"     # free x/y: what dragging/resizing on the paper needs


def default_layout(pack, tree, parent_id):
    """Starting layout for a new child: free placement when the pack has it
    (else its first manager), one line below the existing children. {} when
    the pack has no layouts."""
    if not pack.layouts:
        return {}
    manager = PREFERRED_MANAGER if PREFERRED_MANAGER in pack.layouts else next(iter(pack.layouts))
    n = len(tree.find(parent_id)["children"])
    layout = {"manager": manager}
    keys = {p["key"] for p in pack.layouts[manager]["props"]}
    if "row" in keys and "column" in keys:
        layout.update(row=n, column=0)
    elif "x" in keys and "y" in keys:
        layout.update(x=10, y=10 + 34 * n)
    return layout


def add_widget(tree, pack, wtype, selected_id=None):
    """Add one widget of `wtype` with the pack's defaults. Returns its id, or
    None when the type is unknown or can't be added (root types)."""
    w = pack.widget(wtype)
    if w is None or wtype in pack.root_types:
        return None
    parent_id = add_target(tree, pack, selected_id)
    return tree.add(parent_id, wtype, props=pack.defaults(wtype),
                    layout=default_layout(pack, tree, parent_id),
                    design={"w": w["default_size"][0], "h": w["default_size"][1]})


def move_sibling(tree, widget_id, delta):
    """Move a widget up/down among its siblings. Returns True if it moved."""
    parent = tree.parent_of(widget_id)
    if parent is None:
        return False
    kids = parent["children"]
    i = next(k for k, c in enumerate(kids) if c["id"] == widget_id)
    j = i + delta
    if not 0 <= j < len(kids):
        return False
    tree.move(widget_id, parent["id"], j)
    return True


def coerce_value(kind, text):
    """(ok, value) for text typed into a property field. An empty field means
    'unset' and gives (True, None). Bad numbers give (False, None)."""
    text = (text or "").strip()
    if text == "":
        return True, None
    try:
        if kind == "int":
            return True, int(text)
        if kind == "float":
            return True, float(text)
    except ValueError:
        return False, None
    if kind == "bool":
        return True, text.lower() in ("1", "true", "yes", "on")
    if kind == "list":
        return True, [p.strip() for p in text.split(",") if p.strip()]
    return True, text


def show_value(kind, value):
    """Property value as the text shown in its field."""
    if value is None:
        return ""
    if kind == "list" and isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def outline_rows(tree):
    """[(widget id, parent id or '', label, depth)] depth-first, for the outline."""
    rows = []

    def walk(node, parent_id, depth):
        rows.append((node["id"], parent_id, f"{node['name']}  ({node['type']})", depth))
        for c in node["children"]:
            walk(c, node["id"], depth + 1)
    walk(tree.root, "", 0)
    return rows


# ---- dragging and resizing on the paper ---------------------------------
def _manager(node):
    lay = node["layout"]
    m = lay.get("manager")
    if m is None and ("row" in lay or "column" in lay):
        return "grid"
    if m is None and ("x" in lay or "y" in lay):
        return "place"
    return m


def _int_prop(pack, wtype, key):
    w = pack.widget(wtype)
    return bool(w) and any(p["key"] == key and p["kind"] == "int" for p in w["props"])


def can_move(tree, widget_id):
    node = tree.find(widget_id)
    return node is not None and widget_id != tree.root["id"] and _manager(node) in ("grid", "place")


def resize_edges(tree, pack, widget_id):
    """Edges of the widget that can be dragged: 'nsew' for place, for grid
    'e'/'s' only when the widget has a width/height setting, '' otherwise."""
    node = tree.find(widget_id)
    if node is None or widget_id == tree.root["id"]:
        return ""
    m = _manager(node)
    if m == "place":
        return "nsew"
    if m == "grid":
        return (("s" if node["type"] in ("text", "listbox") and _int_prop(pack, node["type"], "height") else "")
                + ("e" if _int_prop(pack, node["type"], "width") else ""))
    return ""


def handle_at(box, edges, x, y, tol=HANDLE):
    """Which allowed edges ('n', 'se', ...) the point is on, or ''. x/y and tol in paper units."""
    x0, y0, x1, y1 = box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]
    if not (x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol):
        return ""
    hit = ""
    if "n" in edges and abs(y - y0) <= tol:
        hit += "n"
    elif "s" in edges and abs(y - y1) <= tol:
        hit += "s"
    if "w" in edges and abs(x - x0) <= tol:
        hit += "w"
    elif "e" in edges and abs(x - x1) <= tol:
        hit += "e"
    return hit


def resize_box(box, handle, dx, dy):
    """(x, y, w, h) of `box` with the `handle` edges pulled by dx/dy."""
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    if "e" in handle:
        w = max(MIN_SIZE, w + dx)
    if "s" in handle:
        h = max(MIN_SIZE, h + dy)
    if "w" in handle:
        d = min(dx, w - MIN_SIZE)
        x, w = x + d, w - d
    if "n" in handle:
        d = min(dy, h - MIN_SIZE)
        y, h = y + d, h - d
    return x, y, w, h


def _parent_box(tree, boxes, widget_id):
    parent = tree.parent_of(widget_id)
    return parent, next(b for b in boxes if b["id"] == parent["id"])


def _track(starts, sizes, pos):
    """Grid index at a relative position: the last track starting at or
    before it, or one past the last when it lies beyond the end."""
    keys = sorted(starts)
    if not keys:
        return 0
    last = keys[-1]
    if pos >= starts[last] + sizes[last]:
        return last + 1
    found = keys[0]
    for k in keys:
        if pos >= starts[k]:
            found = k
    return found


def drop_container(tree, pack, boxes, widget_id, x, y):
    """Id of the deepest container box at paper point x/y that the widget
    may go into (never itself or one of its own children)."""
    inside = {n["id"] for n in tree.walk(tree.find(widget_id))}
    for b in reversed(boxes):
        if b["id"] in inside or not pack.is_container(b["type"]):
            continue
        if b["x"] <= x <= b["x"] + b["w"] and b["y"] <= y <= b["y"] + b["h"]:
            return b["id"]
    return tree.root["id"]


def move_changes(tree, paper, boxes, widget_id, x, y, w, h, pack=None):
    """Changes (for UITree.edit_many) that put the widget's top-left at paper
    point x/y. Dropped (box centre) over another container: it moves in
    there. Place: pixel position in its parent. Grid: the cell under the
    box centre; a widget already there swaps cells with it."""
    node = tree.find(widget_id)
    parent, pbox = _parent_box(tree, boxes, widget_id)
    m = _manager(node)
    if pack is not None:
        target = drop_container(tree, pack, boxes, widget_id, x + w / 2, y + h / 2)
        if target != parent["id"]:
            tbox = next(b for b in boxes if b["id"] == target)
            if m == "grid":
                layout = {"manager": "grid", "row": len(tree.find(target)["children"]), "column": 0}
            else:
                layout = {"manager": "place", "x": max(0, round(x - tbox["x"])), "y": max(0, round(y - tbox["y"]))}
                for k in ("width", "height"):
                    if k in node["layout"]:
                        layout[k] = node["layout"][k]
            return {widget_id: {"parent": target, "layout": layout}}
    if m == "place":
        return {widget_id: {"layout": {"x": max(0, round(x - pbox["x"])), "y": max(0, round(y - pbox["y"]))}}}
    if m != "grid":
        return {}
    xs, cols, ys, rows = paper.tracks.get(parent["id"], ({}, {}, {}, {}))
    col = _track(xs, cols, x + w / 2 - pbox["x"])
    row = _track(ys, rows, y + h / 2 - pbox["y"])
    lay = node["layout"]
    old = (lay.get("row", 0), lay.get("column", 0))
    if (row, col) == old:
        return {}
    changes = {widget_id: {"layout": {"row": row, "column": col}}}
    for c in parent["children"]:
        cl = c["layout"]
        if c["id"] != widget_id and _manager(c) == "grid" and (cl.get("row", 0), cl.get("column", 0)) == (row, col):
            changes[c["id"]] = {"layout": {"row": old[0], "column": old[1]}}
    return changes


def resize_changes(tree, pack, boxes, widget_id, x, y, w, h):
    """Changes for a widget resized to the paper box x/y/w/h. Place: x, y,
    width, height. Grid: the width / height settings (characters / lines,
    the inverse of ui_paper.natural_size)."""
    node = tree.find(widget_id)
    m = _manager(node)
    if m == "place":
        _parent, pbox = _parent_box(tree, boxes, widget_id)
        return {widget_id: {"layout": {"x": max(0, round(x - pbox["x"])), "y": max(0, round(y - pbox["y"])),
                                       "width": round(w), "height": round(h)}}}
    if m != "grid":
        return {}
    edges, props = resize_edges(tree, pack, widget_id), {}
    k = ui_paper.parse_font(node["props"].get("font"))[1] / ui_paper.DEFAULT_FONT[1]
    if "e" in edges:
        props["width"] = max(1, round((w - 10) / (7 * k)))
    if "s" in edges:
        props["height"] = max(1, round((h - 8) / (16 * k)))
    return {widget_id: {"props": props}} if props else {}
