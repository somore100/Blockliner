"""Pure helpers for canvas zoom and the coordinate grid (no Tk)."""
import math

ZOOM_MIN = 0.2
ZOOM_MAX = 4.0
ZOOM_STEP = 1.1

# Grid spacing candidates in model units; the smallest one that is at least
# MIN_GRID_PX apart on screen is used, so the grid stays readable at any zoom.
GRID_STEPS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 100000]
MIN_GRID_PX = 40


# Below this zoom, boxes are drawn compact (coloured title only) when the
# "hide details when zoomed out" setting is on - fonts and paddings stop
# shrinking at small sizes, so full boxes would balloon and overlap.
LOD_ZOOM = 0.6


def compact_at(zoom, enabled=True):
    try:
        return bool(enabled) and float(zoom) < LOD_ZOOM
    except (TypeError, ValueError):
        return False


# What a box looks like when zoomed out past LOD_ZOOM (setting "lod_mode"):
# "details" = the full box, just smaller; "names" = coloured title strip only;
# "gray" = a plain grey box, no text (quietest overview).
LOD_MODE_CHOICES = [
    ("details", "Show all details (boxes just get smaller)"),
    ("names", "Names only (coloured title strip)"),
    ("gray", "Plain gray boxes (no text)"),
]
LOD_MODES = tuple(k for k, _v in LOD_MODE_CHOICES)


def lod_mode(settings):
    """The zoomed-out look from the settings. Older settings only had the
    checkbox "lod_hide_details": on = "names", off = "details"."""
    settings = settings if isinstance(settings, dict) else {}
    mode = settings.get("lod_mode")
    if mode in LOD_MODES:
        return mode
    return "details" if settings.get("lod_hide_details") is False else "names"


def box_look(zoom, mode):
    """How boxes are drawn at this zoom: "full", "names" or "gray"."""
    if mode not in ("names", "gray") or not compact_at(zoom):
        return "full"
    return mode


def clamp_zoom(z):
    try:
        z = float(z)
    except (TypeError, ValueError):
        return 1.0
    if z != z:   # NaN
        return 1.0
    return max(ZOOM_MIN, min(ZOOM_MAX, z))


def zoom_after_wheel(z, step):
    """step < 0 = wheel up = zoom in, step > 0 = zoom out."""
    return clamp_zoom(z / ZOOM_STEP if step > 0 else z * ZOOM_STEP) if step else clamp_zoom(z)


def grid_step(zoom, min_px=MIN_GRID_PX):
    for s in GRID_STEPS:
        if s * zoom >= min_px:
            return s
    return GRID_STEPS[-1]


def grid_values(lo, hi, step):
    """Multiples of `step` inside [lo, hi] (model units)."""
    if step <= 0 or hi < lo:
        return []
    first = math.ceil(lo / step)
    last = math.floor(hi / step)
    if last - first > 400:       # absurd request (huge window, tiny step): refuse
        return []
    return [k * step for k in range(first, last + 1)]


def anchor_view_origin(anchor_model, screen_pt, zoom):
    """Canvas coordinate that must sit at the canvas's top-left so that
    `anchor_model` (model units) appears at `screen_pt` (pixels) at `zoom`."""
    return anchor_model * zoom - screen_pt
