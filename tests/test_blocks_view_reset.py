"""Blocks layer: a pan offset left over from the Nodes layer must not hide the blocks.
Headless (Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]; tab["file_view_path"] = []
    app.project_blocks.append(("comment", {"text": "hello"}))
    c = app.workspace_canvas
    app.refresh_workspace(); app.update(); app.update()
    check("fresh: view at the origin", c.canvasx(0) == 0 and c.canvasy(0) <= 1)
    app.switch_to_file_view(); app.update()
    app._set_view_origin(900, 700); app.update()
    check("setup: view panned away", c.canvasx(0) > 800)
    app.view_mode = "node"; app.refresh_workspace(); app.update(); app.update(); app.update()
    check("Blocks layer: view back at x = 0", c.canvasx(0) == 0)
    check("Blocks layer: view back at the top", c.canvasy(0) <= 1)
    blk = [w for w in app.workspace_frame.winfo_children() if w.winfo_ismapped()]
    check("block is on screen", bool(blk) and 0 <= blk[0].winfo_rooty() - c.winfo_rooty() < c.winfo_height())
    app._set_view_origin(0, 0); app.update()
    app.refresh_workspace(); app.update(); app.update()
    check("a refresh in the same layer keeps the view", c.canvasx(0) == 0 and c.canvasy(0) <= 1)
    app.destroy()
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
