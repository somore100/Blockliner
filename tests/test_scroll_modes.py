"""Scroll mode setting: smooth (default) vs rigid (snap block to block).
Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI, make_node, normalize_orders
from ui_common import DEFAULT_SETTINGS
from ui_widgets import BlockWidget
import scroll_modes as sm
import ui_palette

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def walk(w):
    for c in w.winfo_children():
        yield c; yield from walk(c)

DOWN = NS(num=5, delta=0); UP = NS(num=4, delta=0)
WIN_DOWN = NS(num=0, delta=-120); WIN_UP = NS(num=0, delta=120); NONE = NS(num=0, delta=0)

def main():
    # ---- pure ----
    t = [0, 100, 250, 250, 400]
    check("pure: next down", sm.next_snap(t, 0, 1) == 100)
    check("pure: next down from between", sm.next_snap(t, 120, 1) == 250)
    check("pure: next down at end = None", sm.next_snap(t, 400, 1) is None)
    check("pure: up from between", sm.next_snap(t, 120, -1) == 100)
    check("pure: up at top = None", sm.next_snap(t, 0, -1) is None)
    check("pure: item within eps counts as 'here'", sm.next_snap(t, 99.5, 1) == 250 and sm.next_snap(t, 100.5, -1) == 0)
    check("pure: empty = None", sm.next_snap([], 0, 1) is None and sm.next_snap([], 0, -1) is None)
    check("pure: unsorted input", sm.next_snap([400, 0, 100], 50, 1) == 100)
    check("pure: padding-only first item merges into the top", sm.snap_points([4, 110, 216], 0) == [0, 110, 216])
    check("pure: region top is always a stop", sm.snap_points([], -30) == [-30])
    check("pure: negative region top", sm.snap_points([10, 200], -50) == [-50, 10, 200])
    check("pure: normalize", sm.normalize_mode("rigid") == "rigid" and sm.normalize_mode("smooth") == "smooth"
          and sm.normalize_mode("x") == "smooth" and sm.normalize_mode(None) == "smooth")
    check("default is smooth", DEFAULT_SETTINGS["scroll_mode"] == "smooth")

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800+0+0"); app.update(); app.update()
    saved = []; app.save_app_settings = lambda: saved.append(app.settings.get("scroll_mode"))
    clock = [1000.0]; app._scroll_clock = lambda: clock[0]
    def tick(): clock[0] += 1.0
    tab = app.tabs[0]
    nodes = [make_node(f"n{i}", node_id=f"n{i}", blocks=[("assign_variable", {"variable": f"v{i}", "value": "1"})]) for i in range(30)]
    tab["nodes"] = nodes; tab["file_view_path"] = []; normalize_orders(nodes)
    for i, n in enumerate(nodes):
        n["x"] = 40 + (i % 3) * 300; n["y"] = 40 + (i // 3) * 220
    tab["active_node_id"] = "n0"

    def wheel(canvas, e):
        app._on_mousewheel(e, canvas); app.update()
    def inset(c): return int(str(c.cget("highlightthickness"))) + int(str(c.cget("borderwidth")))
    def top_of(c): return c.canvasy(0) + inset(c)     # real canvas y shown at the top edge
    def ws_top(): return top_of(app.workspace_canvas)

    # ---- Blocks layer ----
    nodes[0]["blocks"][:] = [("assign_variable", {"variable": f"v{i}", "value": str(i)}) for i in range(40)]
    app.goto_layer("nodes"); app.update()          # make sure we really switch layers
    app.open_node("n0"); app.update(); app.update()
    assert app.view_mode == "node" and app.project_blocks is nodes[0]["blocks"]
    app.workspace_canvas.yview_moveto(0.0); app.update()
    tops = sm.snap_points(sorted(w.winfo_y() for w in app.workspace_frame.winfo_children() if isinstance(w, BlockWidget)), 0)
    check("blocks layer: has many blocks", len(tops) >= 20)

    app.settings["scroll_mode"] = "rigid"
    def by(i):  # fresh top of block number i (Tk shifts layout a couple of px as blocks scroll in)
        return [w for w in app.workspace_frame.winfo_children() if isinstance(w, BlockWidget) and w.index == i][0].winfo_y()
    def at(i): return abs(ws_top() - by(i)) <= 3
    ok = True
    for k in range(1, 6):
        tick(); wheel(app.workspace_canvas, DOWN); ok = ok and at(k)
    check("rigid: each wheel-down snaps to the next block top (5 steps)", ok)
    tick(); wheel(app.workspace_canvas, UP)
    check("rigid: wheel-up goes to the previous block", at(4))
    tick(); wheel(app.workspace_canvas, WIN_DOWN)
    check("rigid: Windows/mac delta<0 scrolls down", at(5))
    tick(); wheel(app.workspace_canvas, WIN_UP)
    check("rigid: Windows/mac delta>0 scrolls up", at(4))
    tick(); wheel(app.workspace_canvas, NONE)
    check("rigid: event with no direction does nothing", at(4))
    for _ in range(6): tick(); wheel(app.workspace_canvas, UP)
    check("rigid: up at the top stays at 0", round(ws_top()) == 0)
    # throttle
    before = round(ws_top()); tick(); wheel(app.workspace_canvas, DOWN); wheel(app.workspace_canvas, DOWN); wheel(app.workspace_canvas, DOWN)
    check("rigid: a burst within the throttle window = ONE step", at(1) and before == 0)
    clock[0] += sm.SNAP_THROTTLE_S + 0.001; wheel(app.workspace_canvas, DOWN)
    check("rigid: after the window passes it steps again", at(2))
    # bottom is bounded, never errors
    for _ in range(80): tick(); wheel(app.workspace_canvas, DOWN)
    check("rigid: scrolling far down stays inside the content", app.workspace_canvas.yview()[1] <= 1.0 and ws_top() > tops[10])
    for _ in range(120): tick(); wheel(app.workspace_canvas, UP)
    check("rigid: and all the way back up reaches 0", round(ws_top()) == 0)

    # smooth does NOT snap
    app.settings["scroll_mode"] = "smooth"
    calls = []; real = app.workspace_canvas.yview_scroll
    app.workspace_canvas.yview_scroll = lambda *a: (calls.append(a), real(*a))[1]
    tick(); wheel(app.workspace_canvas, DOWN)
    check("smooth: uses yview_scroll(1, 'units')", calls == [(1, "units")])
    check("smooth: not snapped to a block top", round(ws_top()) not in tops[1:])
    app.workspace_canvas.yview_scroll = real
    for bad in ("garbage", None, 5):
        app.settings["scroll_mode"] = bad; calls.clear()
        app.workspace_canvas.yview_scroll = lambda *a: (calls.append(a), real(*a))[1]
        wheel(app.workspace_canvas, UP); app.workspace_canvas.yview_scroll = real
        check(f"unknown mode {bad!r} behaves like smooth", calls == [(-1, "units")])
    app.settings.pop("scroll_mode", None); calls.clear()
    app.workspace_canvas.yview_scroll = lambda *a: (calls.append(a), real(*a))[1]
    wheel(app.workspace_canvas, DOWN); app.workspace_canvas.yview_scroll = real
    check("missing key behaves like smooth", calls == [(1, "units")])

    # ---- Nodes layer ----
    app.settings["scroll_mode"] = "rigid"
    app.goto_layer("nodes"); app.update(); app.update()
    app.workspace_canvas.yview_moveto(0.0); app.update()
    wins = [i for i in app.workspace_canvas.find_all() if app.workspace_canvas.type(i) == "window"]
    nreg = float(str(app.workspace_canvas.cget("scrollregion")).split()[1])
    ntops = sm.snap_points(sorted({app.workspace_canvas.bbox(i)[1] for i in wins}), nreg)
    check("nodes layer: several rows of node boxes", len(ntops) >= 5)
    tick(); wheel(app.workspace_canvas, DOWN)
    check("nodes layer rigid: snaps to the next node row", round(ws_top()) == round(ntops[1]))
    tick(); wheel(app.workspace_canvas, DOWN)
    check("nodes layer rigid: ...and the next", round(ws_top()) == round(ntops[2]))
    tick(); wheel(app.workspace_canvas, UP)
    check("nodes layer rigid: up goes back", round(ws_top()) == round(ntops[1]))

    # ---- Files layer ----
    app.goto_layer("files"); app.update(); app.update()
    tick(); wheel(app.workspace_canvas, DOWN)
    check("files layer: rigid wheel does not crash", True)

    # ---- Palette ----
    pal = app.palette_canvas
    app.update(); pal.yview_moveto(0.0); app.update()
    ptops = sm.snap_points(sorted(w.winfo_y() for w in app.palette_frame.winfo_children() if w.winfo_ismapped()), 0)
    check("palette has several rows", len(ptops) >= 5)
    tick(); wheel(pal, DOWN)
    check("palette rigid: snaps to the next row", round(top_of(pal)) == ptops[1])
    tick(); wheel(pal, DOWN); tick(); wheel(pal, DOWN)
    check("palette rigid: keeps stepping row by row", round(top_of(pal)) == ptops[3])
    tick(); wheel(pal, UP)
    check("palette rigid: up", round(top_of(pal)) == ptops[2])
    app.settings["scroll_mode"] = "smooth"
    pc = []; preal = pal.yview_scroll; pal.yview_scroll = lambda *a: (pc.append(a), preal(*a))[1]
    tick(); wheel(pal, DOWN); pal.yview_scroll = preal
    check("palette smooth: plain units scroll", pc == [(1, "units")])
    # throttle is per canvas
    app.settings["scroll_mode"] = "rigid"; app.open_node("n0"); app.update(); app.update()
    app.workspace_canvas.yview_moveto(0.0); pal.yview_moveto(0.0); app.update()
    tick(); wheel(app.workspace_canvas, DOWN); wheel(pal, DOWN)
    check("throttle is per canvas (both moved)", ws_top() > 0 and top_of(pal) > 0)

    # ---- Settings dialog row ----
    def open_dialog():
        app.settings_dialog(); app.update(); app.update()
        dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        combos = [w for w in walk(dlg) if isinstance(w, ui_palette.ttk.Combobox) and "Rigid" in str(w.cget("values"))]
        save = [w for w in walk(dlg) if isinstance(w, tk.Button) and "Save" in str(w.cget("text"))][0]
        return dlg, combos, save
    app.settings["scroll_mode"] = "rigid"
    dlg, combos, save = open_dialog()
    check("dialog: exactly one scroll-mode row", len(combos) == 1)
    check("dialog: shows saved choice (Rigid)", combos[0].get().startswith("Rigid"))
    check("dialog: Save still visible", save.winfo_height() > 20 and save.winfo_rooty() + save.winfo_height() <= dlg.winfo_rooty() + dlg.winfo_height())
    combos[0].set(sm.SCROLL_MODE_CHOICES[0][1]); save.invoke(); app.update()
    check("dialog: choosing Smooth + Save persists it", app.settings["scroll_mode"] == "smooth" and saved[-1] == "smooth")
    dlg, combos, save = open_dialog()
    combos[0].set(sm.SCROLL_MODE_CHOICES[1][1]); dlg.event_generate("<Escape>"); app.update()
    check("dialog: Esc does not change it", app.settings["scroll_mode"] == "smooth")
    app.settings["scroll_mode"] = "junk"
    dlg, combos, save = open_dialog()
    check("dialog: junk value shows as Smooth", combos[0].get().startswith("Smooth"))
    save.invoke(); app.update()
    check("dialog: saving repairs junk to smooth", app.settings["scroll_mode"] == "smooth")

    app.destroy()
    print("\nFAILED:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
