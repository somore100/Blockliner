"""Canvas groups (ComfyUI style): coloured, labelled, resizable regions
drawn behind boxes. Pure module (no Tk). Positions/sizes are model units
(the same units as canvas_x / canvas_y)."""

GROUP_COLORS = [
    ("Blue", "#3f789e"), ("Green", "#3f9e6a"), ("Orange", "#c08a3e"),
    ("Red", "#a65050"), ("Purple", "#8a5aa8"), ("Teal", "#3f9e9a"),
    ("Pink", "#a85a8a"), ("Gray", "#7a7a7a"),
]
DEFAULT_COLOR = GROUP_COLORS[0][1]
MIN_W, MIN_H = 120, 80
DEFAULT_W, DEFAULT_H = 320, 220


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e7


def _valid_color(c):
    return (isinstance(c, str) and len(c) == 7 and c[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in c[1:]))


def new_id(existing_ids):
    n = 1
    while f"group_{n}" in existing_ids:
        n += 1
    return f"group_{n}"


def make_group(groups, x, y, label="Group", color=None, w=DEFAULT_W, h=DEFAULT_H, level=""):
    g = {"id": new_id({g["id"] for g in groups}), "label": label,
         "color": color if _valid_color(color) else DEFAULT_COLOR,
         "x": x, "y": y, "w": max(MIN_W, w), "h": max(MIN_H, h), "level": level}
    groups.append(g)
    return g


def normalize_groups(raw, notes=None):
    """Clean a list read from a save file: damaged entries are dropped
    (with a note), sizes clamped, ids made unique. Never raises."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not (isinstance(r, dict) and _num(r.get("x")) and _num(r.get("y"))
                and _num(r.get("w")) and _num(r.get("h"))):
            if notes is not None:
                notes.append("A damaged group was skipped.")
            continue
        gid = r.get("id") if isinstance(r.get("id"), str) and r.get("id") else None
        if gid is None or gid in seen:
            gid = new_id(seen)
        seen.add(gid)
        label = r.get("label")
        out.append({"id": gid, "label": label if isinstance(label, str) else "Group",
                    "color": r["color"] if _valid_color(r.get("color")) else DEFAULT_COLOR,
                    "x": r["x"], "y": r["y"],
                    "w": max(MIN_W, r["w"]), "h": max(MIN_H, r["h"]),
                    "level": r["level"] if isinstance(r.get("level"), str) else ""})
    return out


def groups_for_level(groups, level):
    return [g for g in groups if g.get("level", "") == level]


def resized(g, w, h):
    g["w"], g["h"] = max(MIN_W, w), max(MIN_H, h)


def contains_center(g, x, y, w, h):
    """Is the box (x, y, w, h) 'inside' the group: its centre is."""
    cx, cy = x + w / 2, y + h / 2
    return g["x"] <= cx <= g["x"] + g["w"] and g["y"] <= cy <= g["y"] + g["h"]


def blend(color, bg="#1e1e1e", t=0.2):
    """Opaque stand-in for a translucent fill (Tk canvases have no alpha)."""
    c = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(b[i] + (c[i] - b[i]) * t) for i in range(3))
