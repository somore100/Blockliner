"""Node drag redraws only the wires touching the dragged node (draw_wires_for),
and the result is identical to a full draw_wires(). Run under Xvfb."""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI, make_node, normalize_orders

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def wire_state(app):
    c = app.workspace_canvas
    return sorted((tuple(c.gettags(i)), tuple(round(v, 3) for v in c.coords(i))) for i in c.find_withtag("wire"))

def wire_ids(app, tag): return set(app.workspace_canvas.find_withtag(tag))

def main():
    N = 30; random.seed(3)
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = []
    for i in range(N):
        bl = [("func_call", {"name": f"node_{random.randrange(N)}", "args": ""}) for _ in range(3)]
        nodes.append(make_node(f"node_{i}", node_id=f"n{i}", blocks=bl))
    tab["nodes"] = nodes; tab["active_node_id"] = "n0"; tab["file_view_path"] = []
    app.project_blocks = nodes[0]["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update()
    target = "n7"
    touching = [(n["id"], t) for n in nodes for t in n["references"] if n["id"] == target or t == target]
    others = [(n["id"], t) for n in nodes for t in n["references"] if n["id"] != target and t != target]
    check("setup: target has outgoing and incoming wires", any(s == target for s, _ in touching) and any(t == target for _, t in touching) and others)
    check("setup: wires exist", len(app.workspace_canvas.find_withtag("wire")) > 0)

    # move the node, then compare fast path against the full redraw
    node = next(n for n in nodes if n["id"] == target)
    node["canvas_x"] += 137; node["canvas_y"] -= 41
    wid, _ = app._fileview_boxes[target]; app.workspace_canvas.coords(wid, node["canvas_x"], node["canvas_y"])
    untouched_before = {e: wire_ids(app, f"wire_{e[0]}_{e[1]}") for e in others}
    touched_before = {e: wire_ids(app, f"wire_{e[0]}_{e[1]}") for e in touching}
    app.draw_wires_for(target)
    fast = wire_state(app)
    check("untouched wires were not recreated", all(wire_ids(app, f"wire_{e[0]}_{e[1]}") == ids for e, ids in untouched_before.items()))
    check("touched wires were recreated", all(wire_ids(app, f"wire_{e[0]}_{e[1]}") != ids for e, ids in touched_before.items()))
    app.draw_wires()
    full = wire_state(app)
    check("fast path result == full redraw (tags + coords)", fast == full)
    check("no duplicate wire items", len(fast) == len(set(fast)) or len(fast) == len(full))

    # a real Tk-delivered drag on the box header moves wires live
    app.update()
    hdr = None
    def walk(w):
        nonlocal hdr
        for ch in w.winfo_children():
            if hdr is None and ch.winfo_class() in ("Frame",) and ch.winfo_height() > 0 and ch.bind("<B1-Motion>"): hdr = ch
            walk(ch)
    walk(app._fileview_boxes[target][1])
    if hdr is not None:
        x0 = node["canvas_x"]
        rx, ry = hdr.winfo_rootx() + 5, hdr.winfo_rooty() + 5
        hdr.event_generate("<ButtonPress-1>", x=5, y=5, rootx=rx, rooty=ry)
        hdr.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 60, rooty=ry + 20)
        hdr.event_generate("<B1-Motion>", x=5, y=5, rootx=rx + 90, rooty=ry + 30)
        hdr.event_generate("<ButtonRelease-1>", x=5, y=5, rootx=rx + 90, rooty=ry + 30)
        app.update()
        check("real drag moved the node", node["canvas_x"] != x0)
        live = wire_state(app); app.draw_wires()
        check("after real drag, wires match a full redraw", live == wire_state(app))
    else:
        check("found draggable header", False)

    app.destroy()
    print(); print("FAILED: " + ", ".join(FAILURES) if FAILURES else "ALL OK")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
