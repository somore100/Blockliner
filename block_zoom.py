"""Zoom of the Blocks layer (no Tk): the scale steps, and what the mouse wheel does.

The blocks are ordinary widgets, so zooming means drawing them again with bigger or
smaller fonts and heights (see BlockWidget._f / _px), not scaling a canvas.
"""

STEPS = (0.6, 0.7, 0.8, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)
MIN_FONT = 6

WHEEL_CHOICES = [
    ("ctrl", "Wheel scrolls, Ctrl+wheel zooms"),
    ("wheel", "Wheel zooms, Ctrl+wheel scrolls"),
]


def normalize_wheel(value):
    return "wheel" if value == "wheel" else "ctrl"


def wheel_action(mode, ctrl):
    """'zoom' or 'scroll' for a wheel turn in the Blocks layer."""
    zoom_with_ctrl = normalize_wheel(mode) == "ctrl"
    return "zoom" if ctrl == zoom_with_ctrl else "scroll"


def next_scale(current, direction):
    """The step above (direction > 0) or below (direction < 0) `current`; stops at the ends."""
    here = min(range(len(STEPS)), key=lambda i: abs(STEPS[i] - current))
    return STEPS[max(0, min(len(STEPS) - 1, here + (1 if direction > 0 else -1)))]


def scaled_font_size(size, scale):
    return max(MIN_FONT, round(size * scale))


def scaled_px(px, scale):
    return max(1, round(px * scale))
