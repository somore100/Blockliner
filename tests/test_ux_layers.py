"""UX pass: layer bar + keybinds, palette drag-and-drop, right-edge hide
strip. Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui
from ui import BlocklinerUI, PaletteBlockItem, make_node, keybind_from_event, keybind_label, DARK_ACCENT

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def ev(keysym, state):
    return NS(keysym=keysym, state=state)

def active(app):
    return {k for k, b in app._layer_buttons.items() if str(b.cget("bg")) == DARK_ACCENT}

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800+0+0"); app.update(); app.update()
    tab = app.tabs[0]
    other = make_node("Other", node_id="o1", blocks=[])
    tab["nodes"].append(other)

    # ---------- pure helpers ----------
    check("Ctrl+1 -> Control-Key-1", keybind_from_event(ev("1", 0x4)) == "Control-Key-1")
    check("Ctrl+Alt+x", keybind_from_event(ev("x", 0x4 | 0x8)) == "Control-Alt-Key-x")
    check("bare key rejected (would steal typing)", keybind_from_event(ev("1", 0)) is None)
    check("Shift-only rejected", keybind_from_event(ev("1", 0x1)) is None)
    check("modifier alone rejected", keybind_from_event(ev("Control_L", 0x4)) is None)
    check("label", keybind_label("Control-Key-1") == "Ctrl+1" and keybind_label("Control-Alt-Key-x") == "Ctrl+Alt+x")

    # ---------- layer bar ----------
    check("starts on Blocks: Blocks + Code highlighted", app.view_mode == "node" and active(app) == {"blocks", "code"})
    app.goto_layer("files"); app.update()
    check("Files button -> files layer", app.view_mode == "files" and active(app) == {"files"})
    app.goto_layer("nodes"); app.update()
    check("Nodes button -> nodes layer", app.view_mode == "file" and active(app) == {"nodes"})
    app.goto_layer("blocks"); app.update()
    check("Blocks button -> block editor", app.view_mode == "node" and active(app) == {"blocks", "code"})
    app.goto_layer("blocks"); app.update()
    check("Blocks again is a no-op", app.view_mode == "node")

    # nested navigation resets when jumping to Nodes
    folder = make_node("Folder", node_id="f1", kind="category", child_nodes=[])
    tab["nodes"].append(folder)
    app.goto_layer("nodes"); app.open_node("f1"); app.update()
    check("inside a category", tab["file_view_path"] == ["f1"])
    app.goto_layer("nodes"); app.update()
    check("Nodes from inside a category resets to top", tab["file_view_path"] == [])

    # code toggle per layer
    app.goto_layer("code"); app.update()
    check("Code at Nodes layer toggles code view", app.file_view_code_mode is True and "code" in active(app))
    app.goto_layer("code"); app.update()
    check("Code again toggles back", app.file_view_code_mode is False and "code" not in active(app))
    app.goto_layer("files"); app.goto_layer("code"); app.update()
    check("Code at Files layer toggles code view", app.files_view_code_mode is True and "code" in active(app))
    app.goto_layer("nodes"); app.update()
    check("switching layer from code view lands on the canvas", app.view_mode == "file" and not app.file_view_code_mode)
    app.goto_layer("files"); app.update()
    check("returning to Files lands on its canvas, not the code view", app.view_mode == "files" and not app.files_view_code_mode)
    app.goto_layer("nodes"); app.update()
    app.goto_layer("blocks"); app.update()
    check("Code panel visible at Blocks", app.panels.is_visible("code"))
    app.goto_layer("code"); app.update()
    check("Code at Blocks hides the panel", not app.panels.is_visible("code") and "code" not in active(app))
    app.goto_layer("code"); app.update()
    check("Code at Blocks shows it again", app.panels.is_visible("code"))

    # blocks from files layer opens active node
    app.goto_layer("files"); app.goto_layer("blocks"); app.update()
    check("Blocks from Files layer opens the active node", app.view_mode == "node")

    # ---------- keybinds ----------
    app.focus_force(); app.update()
    app.goto_layer("blocks")
    app.event_generate("<Control-Key-1>"); app.update()
    check("Ctrl+1 -> Files", app.view_mode == "files")
    app.event_generate("<Control-Key-2>"); app.update()
    check("Ctrl+2 -> Nodes", app.view_mode == "file")
    app.event_generate("<Control-Key-3>"); app.update()
    check("Ctrl+3 -> Blocks", app.view_mode == "node")
    app.event_generate("<Control-Key-4>"); app.update()
    check("Ctrl+4 -> toggles Code", not app.panels.is_visible("code"))
    app.event_generate("<Control-Key-4>"); app.update()

    app.settings["keybinds"] = {"layer_files": "Control-Alt-Key-f"}
    app.apply_keybinds()
    binds = app.get_keybinds()
    check("partial saved keybinds fall back to defaults", binds["layer_files"] == "Control-Alt-Key-f" and binds["layer_nodes"] == "Control-Key-2")
    app.event_generate("<Control-Alt-Key-f>"); app.update()
    check("custom keybind works", app.view_mode == "files")
    app.goto_layer("blocks"); app.update()
    app.event_generate("<Control-Key-1>"); app.update()
    check("old keybind no longer fires", app.view_mode == "node")

    # modal dialog holds the grab: shortcuts ignored
    dlg = tk.Toplevel(app); dlg.grab_set(); app.update()
    app.event_generate("<Control-Key-2>"); app.update()
    check("shortcuts ignored while a modal dialog is open", app.view_mode == "node")
    dlg.destroy(); app.update()

    # ---------- palette drag & drop ----------
    app.goto_layer("blocks"); app.update()
    wx = app.workspace_canvas.winfo_rootx() + 60; wy = app.workspace_canvas.winfo_rooty() + 60
    px = app.palette_canvas.winfo_rootx() + 60; py = app.palette_canvas.winfo_rooty() + 60
    check("drop target: over workspace at Blocks layer", app.can_drop_block_at(wx, wy))
    check("drop target: over palette is not valid", not app.can_drop_block_at(px, py))
    check("drop target: far outside is not valid", not app.can_drop_block_at(-50, -50))
    app.goto_layer("nodes"); app.update()
    check("drop target: not valid at Nodes layer", not app.can_drop_block_at(wx, wy))
    app.goto_layer("blocks"); app.update()

    module = next(iter(app.blocks.values()))
    calls = []
    item2 = PaletteBlockItem(app.palette_frame, module, calls.append, app.can_drop_block_at)
    nodrop = PaletteBlockItem(app.palette_frame, module, calls.append)

    item2._drag_press(NS(x_root=px, y_root=py)); item2._drag_release(NS(x_root=px, y_root=py))
    check("plain click still adds", len(calls) == 1)

    item2._drag_press(NS(x_root=px, y_root=py))
    item2._drag_motion(NS(x_root=px + 2, y_root=py + 2))
    check("tiny movement is not a drag", item2._ghost is None)
    item2._drag_motion(NS(x_root=px + 30, y_root=py + 30)); app.update()
    check("real movement starts a drag with a ghost", item2._ghost is not None)
    item2._drag_motion(NS(x_root=wx, y_root=wy)); app.update()
    check("ghost shows no cross over a valid target", "\u2715" not in item2._ghost_label.cget("text"))
    item2._drag_motion(NS(x_root=px, y_root=py)); app.update()
    check("ghost shows a cross over an invalid target", "\u2715" in item2._ghost_label.cget("text"))
    item2._drag_release(NS(x_root=wx, y_root=wy)); app.update()
    check("drop on workspace adds the block", len(calls) == 2)
    check("ghost is destroyed after drop", item2._ghost is None)

    item2._drag_press(NS(x_root=px, y_root=py)); item2._drag_motion(NS(x_root=px + 40, y_root=py + 40))
    item2._drag_release(NS(x_root=px + 40, y_root=py + 40)); app.update()
    check("drop on the palette itself adds nothing", len(calls) == 2 and item2._ghost is None)

    n0 = len(calls)
    nodrop._drag_press(NS(x_root=px, y_root=py)); nodrop._drag_motion(NS(x_root=wx, y_root=wy))
    nodrop._drag_release(NS(x_root=wx, y_root=wy)); app.update()
    check("an item without a drop check never adds on drag", len(calls) == n0 and nodrop._ghost is None)
    app.goto_layer("nodes"); app.update()
    item2._drag_press(NS(x_root=px, y_root=py)); item2._drag_motion(NS(x_root=wx, y_root=wy + 40))
    item2._drag_release(NS(x_root=wx, y_root=wy + 40)); app.update()
    check("drop at Nodes layer adds nothing", len(calls) == 2)
    app.goto_layer("blocks"); app.update()

    # real event path: press/motion/release delivered through Tk's own bindings
    app.goto_layer("blocks"); app.update()
    app.refresh_palette(); app.update()
    real_add = app.add_block_to_workspace
    dropped = []
    app.add_block_to_workspace = lambda m, c=None: dropped.append(m)
    try:
        app.refresh_palette(); app.update()
        items = []
        def find(w):
            for ch in w.winfo_children():
                if isinstance(ch, PaletteBlockItem): items.append(ch)
                find(ch)
        find(app.palette_frame)
        check("palette has items", len(items) > 0)
        it = items[0]
        it.update_idletasks()
        lab = it.name_label
        sx, sy = lab.winfo_rootx() + 4, lab.winfo_rooty() + 4
        lab.event_generate("<ButtonPress-1>", x=4, y=4, rootx=sx, rooty=sy)
        lab.event_generate("<B1-Motion>", x=4, y=4, rootx=sx + 40, rooty=sy + 10)
        app.update()
        check("Tk-delivered motion creates the ghost", it._ghost is not None)
        lab.event_generate("<B1-Motion>", x=4, y=4, rootx=wx, rooty=wy)
        lab.event_generate("<ButtonRelease-1>", x=4, y=4, rootx=wx, rooty=wy)
        app.update()
        check("Tk-delivered drop onto the workspace adds exactly one block", len(dropped) == 1 and it._ghost is None)
        lab.event_generate("<ButtonPress-1>", x=4, y=4, rootx=sx, rooty=sy)
        lab.event_generate("<ButtonRelease-1>", x=4, y=4, rootx=sx, rooty=sy)
        app.update()
        check("Tk-delivered plain click adds exactly one more", len(dropped) == 2)
    finally:
        app.add_block_to_workspace = real_add

    # ---------- right-edge strip ----------
    app.goto_layer("blocks"); app.update()
    check("right strip visible at Blocks layer", app._code_strip_shown and app.code_strip.winfo_ismapped())
    check("glyph points right when panel is open", app.code_strip_glyph.cget("text") == "\u25b8")
    app.code_strip.event_generate("<Button-1>"); app.update()
    check("clicking the strip hides the code panel", not app.panels.is_visible("code"))
    check("glyph flips when hidden", app.code_strip_glyph.cget("text") == "\u25c2")
    check("strip stays so it can be reopened", app.code_strip.winfo_ismapped())
    app.code_strip_glyph.event_generate("<Button-1>"); app.update()
    check("clicking again shows it", app.panels.is_visible("code"))
    app.goto_layer("nodes"); app.update()
    check("right strip hidden outside the Blocks layer", not app._code_strip_shown and not app.code_strip.winfo_ismapped())
    app.goto_layer("blocks"); app.update()
    check("right strip returns at Blocks layer", app.code_strip.winfo_ismapped())
    app.toggle_palette(); app.update()
    check("left strip still hides the palette", not app.panels.is_visible("palette"))
    app.toggle_palette(); app.update()

    app.destroy()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED"); [print(" -", f) for f in FAILURES]; sys.exit(1)
    print("All UX layer tests passed.")

main()
