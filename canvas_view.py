"""Pure helpers for canvas zoom and the coordinate grid (no Tk)."""
import math

ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
ZOOM_STEP = 1.1

# Grid spacing candidates in model units; the smallest one that is at least
# MIN_GRID_PX apart on screen is used, so the grid stays readable at any zoom.
GRID_STEPS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 100000]
MIN_GRID_PX = 40


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
