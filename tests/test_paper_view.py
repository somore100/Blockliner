"""Designer camera maths: fit, zoom about a point, pan limits (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import paper_view as V

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

def near(a, b):
    return abs(a - b) < 1e-6

# fit keeps the old behaviour: shrinks, never grows, centred horizontally
s, ox, oy = V.fit((1000, 800), (400, 300), 14)
check("a small paper is not grown", s == 1.0 and near(ox, 300) and oy == 14)
s, ox, oy = V.fit((300, 300), (600, 800), 14)
check("a large paper is shrunk to fit", s < 0.5 and s >= V.ZOOM_MIN and ox >= 14)
check("never smaller than the minimum", V.fit((50, 50), (4000, 4000), 14)[0] == V.ZOOM_MIN)

# zooming keeps the point under the pointer still
origin, scale, anchor = (40.0, 20.0), 1.0, (240.0, 120.0)
paper_pt = ((anchor[0] - origin[0]) / scale, (anchor[1] - origin[1]) / scale)
for new in (0.5, 2.0, 3.7):
    o = V.zoom_about(scale, origin, anchor, new)
    check(f"zoom to {new} keeps the pointer's paper point", near(o[0] + paper_pt[0] * new, anchor[0]) and near(o[1] + paper_pt[1] * new, anchor[1]))

# the paper can't be lost off screen
canvas, paper = (800, 600), (400, 300)
check("far right: some paper stays visible", V.clamp_origin((5000, 0), 1.0, paper, canvas)[0] == 800 - V.KEEP)
check("far left: some paper stays visible", V.clamp_origin((-5000, 0), 1.0, paper, canvas)[0] == V.KEEP - 400)
check("far down and up", V.clamp_origin((0, 5000), 1.0, paper, canvas)[1] == 600 - V.KEEP
      and V.clamp_origin((0, -5000), 1.0, paper, canvas)[1] == V.KEEP - 300)
check("a visible paper is left alone", V.clamp_origin((100, 50), 1.0, paper, canvas) == (100, 50))
check("zoomed in, panning reaches the far corner", V.clamp_origin((-5000, -5000), 4.0, paper, canvas) == (V.KEEP - 1600, V.KEEP - 1200))
check("a tiny paper is kept whole on screen", V.clamp_origin((-100, 0), 0.2, (100, 100), (800, 600)) == (0, 0))

check("scale is clamped", V.clamp_scale(99) == V.ZOOM_MAX and V.clamp_scale(0) == V.ZOOM_MIN and V.clamp_scale("x") == 1.0 and V.clamp_scale(float("nan")) == 1.0)
check("percent text", V.percent(1.0) == "100%" and V.percent(0.256) == "26%")

print("ALL OK" if not fails else f"FAILURES: {fails}")
