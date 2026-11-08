"""Pure test: block zoom steps and the wheel choice (block_zoom.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import block_zoom as bz

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


check("zooming in from 100% goes to the next step", bz.next_scale(1.0, 1) == 1.15)
check("zooming out from 100% goes to the previous step", bz.next_scale(1.0, -1) == 0.9)
check("it stops at the largest step", bz.next_scale(2.0, 1) == 2.0)
check("it stops at the smallest step", bz.next_scale(0.6, -1) == 0.6)
check("a value between steps snaps to the nearest first", bz.next_scale(1.02, 1) == 1.15)
check("fonts scale but never below the minimum", bz.scaled_font_size(10, 1.5) == 15 and bz.scaled_font_size(8, 0.6) == bz.MIN_FONT)
check("heights scale", bz.scaled_px(32, 1.5) == 48 and bz.scaled_px(1, 0.6) == 1)
check("default: the wheel scrolls", bz.wheel_action("ctrl", False) == "scroll")
check("default: Ctrl+wheel zooms", bz.wheel_action("ctrl", True) == "zoom")
check("swapped: the wheel zooms", bz.wheel_action("wheel", False) == "zoom")
check("swapped: Ctrl+wheel scrolls", bz.wheel_action("wheel", True) == "scroll")
check("an unknown setting means the default", bz.wheel_action("zzz", True) == "zoom")
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
