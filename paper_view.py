"""Camera maths for the UI designer's paper: fit, zoom, pan (pure, no Tk).

The paper is drawn at `scale` with its top-left corner at `origin` (pixels on
the canvas). With no manual view the paper is fitted (shrunk, never grown, and
centred). Zooming keeps the point under the pointer still; panning moves the
origin; the origin is kept so that some of the paper always stays in view.
"""
ZOOM_MIN = 0.2
ZOOM_MAX = 4.0
BUTTON_STEP = 1.25          # one press of the + / - buttons
KEEP = 80                   # px of paper that must stay on screen


def clamp_scale(s):
    try:
        s = float(s)
    except (TypeError, ValueError):
        return 1.0
    if s != s:
        return 1.0
    return max(ZOOM_MIN, min(ZOOM_MAX, s))


def fit(canvas_size, paper_size, margin):
    """(scale, ox, oy): the whole paper visible, shrunk but never grown."""
    cw, ch = canvas_size
    pw, ph = paper_size
    s = max(ZOOM_MIN, min(1.0, (cw - 2 * margin - 3) / pw, (ch - 2 * margin - 3) / ph))
    return s, max(margin, (cw - pw * s) / 2), margin


def zoom_about(scale, origin, anchor, new_scale):
    """The origin that keeps the paper point under `anchor` (canvas px) where it
    is while the scale goes from `scale` to `new_scale`."""
    ax, ay = anchor
    ox, oy = origin
    px, py = (ax - ox) / scale, (ay - oy) / scale
    return ax - px * new_scale, ay - py * new_scale


def clamp_origin(origin, scale, paper_size, canvas_size, keep=KEEP):
    """Move the origin the least that leaves at least `keep` px of the paper on
    the canvas (or all of it, if the paper is smaller than that)."""
    ox, oy = origin
    cw, ch = canvas_size
    pw, ph = paper_size[0] * scale, paper_size[1] * scale
    kx, ky = min(keep, pw, cw), min(keep, ph, ch)
    ox = max(kx - pw, min(cw - kx, ox))
    oy = max(ky - ph, min(ch - ky, oy))
    return ox, oy


def percent(scale):
    return f"{round(scale * 100)}%"
