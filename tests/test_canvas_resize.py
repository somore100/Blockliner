"""Node box resize + zoom speed (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import canvas_view as C
import project_file

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    check("east edge grows width only", C.resize_node_rect(10, 10, 200, 100, "e", 30, 50) == (10, 10, 230, 100))
    check("west edge moves x, right side stays", C.resize_node_rect(10, 10, 200, 100, "w", 30, 0) == (40, 10, 170, 100))
    check("north-west corner", C.resize_node_rect(10, 10, 200, 100, "nw", -20, -10) == (-10, 0, 220, 110))
    x, y, w, h = C.resize_node_rect(10, 10, 200, 100, "nw", 500, 500)
    check("never below the minimum, opposite corner fixed", (w, h) == (C.NODE_MIN_W, C.NODE_MIN_H) and x + w == 210 and y + h == 110)
    check("zoom speed setting", C.zoom_factor({"zoom_speed": "fast"}) > C.zoom_factor({}) == C.zoom_factor({"zoom_speed": "nope"}))
    check("slow wheel step is smaller than the old one", C.zoom_after_wheel(1.0, -1, C.zoom_factor({})) < C.zoom_after_wheel(1.0, -1))
    node = project_file._node_from_json({"id": "a", "name": "a", "kind": "function", "blocks": [],
                                         "canvas_x": 1, "canvas_y": 2, "canvas_w": 300, "canvas_h": 150}, set(), [])
    check("project file keeps the node size", (node.get("canvas_w"), node.get("canvas_h")) == (300, 150))
    print("\nFAILURES:", FAILURES)

main()
