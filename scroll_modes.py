"""Pure helpers for the "rigid" scroll mode (no Tk in here).

Rigid mode: one wheel step snaps the view so the next (or previous) item
sits at the top, instead of moving a few pixels. `tops` are the y
positions (in canvas coordinates) of the items that can be snapped to.
"""

SCROLL_MODE_CHOICES = [
    ("smooth", "Smooth (continuous, like a web page)"),
    ("rigid", "Rigid (snap block to block)"),
]
SNAP_EPS = 1.0          # px: an item within this of the top counts as "at the top"
SNAP_THROTTLE_S = 0.05  # trackpads fire dozens of events per flick; one step per 50 ms


TOP_MERGE_PX = 48       # items this close to the very top count as "the top"


def snap_points(tops, region_top):
    """Stops for rigid scrolling: the very top of the content, then every
    item that is not just top padding (so the first wheel step doesn't
    waste itself on a few pixels)."""
    return [region_top] + [t for t in tops if t - region_top > TOP_MERGE_PX]


def normalize_mode(value):
    """Anything unknown behaves like the default, smooth."""
    return "rigid" if value == "rigid" else "smooth"


def next_snap(tops, current, direction, eps=SNAP_EPS):
    """Return the item top to snap to, or None if there is nothing further.

    direction > 0 = scroll down (next item), < 0 = scroll up (previous item).
    """
    ordered = sorted(set(tops))
    if direction > 0:
        for t in ordered:
            if t > current + eps:
                return t
    else:
        for t in reversed(ordered):
            if t < current - eps:
                return t
    return None
