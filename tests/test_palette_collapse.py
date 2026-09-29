"""Left-palette collapse via the edge strip (toggle_palette + strip glyph)."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800"); app.update()
    pm = app.panels
    strip, glyph = app.palette_strip, app.palette_strip_glyph
    ws = lambda: pm.frame("workspace").winfo_width()

    check("strip is visible and thin", strip.winfo_ismapped() and strip.winfo_width() == 16)
    check("strip is full height", strip.winfo_height() > 300)
    check("strip sits left of the palette", strip.winfo_rootx() + strip.winfo_width() <= pm.frame("palette").winfo_rootx())
    check("glyph starts as collapse arrow", glyph.cget("text") == "\u25c2")
    check("click is bound on strip and glyph",
          bool(strip.bind("<Button-1>")) and bool(glyph.bind("<Button-1>")))

    w0 = ws()
    app.toggle_palette(); app.update()
    check("collapse hides the palette", pm.is_visible("palette") is False)
    check("glyph flips to expand arrow", glyph.cget("text") == "\u25b8")
    check("strip stays on screen while collapsed", strip.winfo_ismapped() and strip.winfo_width() == 16)
    check("workspace gains the palette's width", ws() >= w0 + 280)

    app.toggle_palette(); app.update()
    check("expand shows the palette again", pm.is_visible("palette") is True)
    check("glyph flips back", glyph.cget("text") == "\u25c2")
    check("palette back at 280px and workspace restored",
          pm.frame("palette").winfo_width() == 280 and abs(ws() - w0) <= 1)

    # Width memory through a collapse
    pm.set_width("palette", 350); app.update()
    app.toggle_palette(); app.toggle_palette(); app.update()
    check("resized palette reopens at its resized width", abs(pm.frame("palette").winfo_width() - 350) <= 2)
    pm.set_width("palette", 280); app.update()

    # Rapid toggling + layer switches while collapsed
    for _ in range(7): app.toggle_palette()
    app.update()
    check("odd number of toggles leaves it collapsed", pm.is_visible("palette") is False
          and glyph.cget("text") == "\u25b8")
    app.switch_to_file_view(); app.update()
    app.switch_to_files_view(); app.update()
    app.view_mode = "node"; app.update_right_panel_visibility(); app.update()
    check("layer switches don't re-open a collapsed palette", pm.is_visible("palette") is False)
    check("code panel still follows its layer", pm.is_visible("code") is True)

    # Collapsed palette must not break block adding / search state
    app.toggle_palette(); app.update()
    check("palette content survives collapse/expand", len(app.palette_frame.winfo_children()) > 0)

    # Hover styling round trip
    app._palette_strip_hover(True); app.update()
    hot = strip.cget("bg")
    app._palette_strip_hover(False); app.update()
    check("hover changes then restores strip colour", hot != strip.cget("bg"))

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All palette-collapse tests passed.")

main()
