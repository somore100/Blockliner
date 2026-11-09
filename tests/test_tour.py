"""Pure test: the first-run tour's steps, navigation and card placement (tour.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour as T

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


ids = [s["id"] for s in T.STEPS]
check("step ids are unique", len(ids) == len(set(ids)))
check("every step has a title and text", all(s["title"] and s["text"] for s in T.STEPS))
check("the first step is a centred welcome", T.STEPS[0]["target"] is None)
check("targets are known names", {s["target"] for s in T.STEPS} <= {None, "layers", "palette", "workspace", "code", "run", "tabs", "menus"})

t = T.Tour()
check("starts on the first step", t.first and not t.last and t.progress() == f"1 / {len(T.STEPS)}")
check("back on the first step does nothing", t.back() is False and t.index == 0)
while t.next():
    pass
check("next walks to the last step", t.last and t.index == len(T.STEPS) - 1)
check("next on the last step says the tour is over", t.next() is False)
check("back goes one step", t.back() and t.index == len(T.STEPS) - 2)

W, H = 1200, 800
check("a centred card is centred", T.card_position(None, (300, 200), (W, H)) == (450, 300))
check("the card goes to the right of a narrow part", T.card_position((10, 100, 200, 400), (300, 200), (W, H)) == (224, 100))
x, y = T.card_position((900, 100, 290, 400), (300, 200), (W, H))
check("no room on the right: it goes to the left", x == 900 - 300 - 14 and y == 100)
x, y = T.card_position((10, 10, 1180, 40), (300, 200), (W, H))
check("a wide bar: the card goes below", y == 10 + 40 + 14 and 0 <= x <= W - 300)
x, y = T.card_position((10, 10, 1180, 780), (300, 200), (W, H))
check("a part as big as the window: the card sits inside its corner", (x, y) == (34, 34))
x, y = T.card_position((10, 700, 1180, 90), (300, 200), (W, H))
check("near the bottom the card goes above", y == 700 - 200 - 14)
x, y = T.card_position((5, 5, 50, 50), (2000, 2000), (W, H))
check("a card bigger than the window stays at the top-left", (x, y) == (0, 0))
rects = T.outline_rects((100, 100, 50, 40), 3)
check("the outline is four rectangles around the part", len(rects) == 4 and rects[0] == (97, 97, 56, 3) and rects[1] == (97, 140, 56, 3))
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
