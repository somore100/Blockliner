"""Panel manager tests (panels.py) + integration with the main window.

Headless: run under Xvfb (see runtests). Exits non-zero on any failure.
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from panels import PanelManager, PanelSpec

FAILURES = []


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILURES.append(label)


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    except Exception:
        return False
    return False


def screen_order(pm):
    """Visible panel ids left-to-right, as actually laid out by Tk."""
    vis = [i for i in pm.ids() if pm.is_visible(i)]
    return sorted(vis, key=lambda i: pm.frame(i).winfo_x())


def unit_tests():
    root = tk.Tk()
    root.geometry("1200x600")
    pm = PanelManager(root, bg="#111111")
    pm.paned.pack(fill=tk.BOTH, expand=True)

    events = []
    pm.add_listener(lambda pid, vis: events.append((pid, vis)))

    # Register OUT of dock order on purpose: right, left, center.
    pm.create_panel(PanelSpec("code", "Code", dock="right", width=300, min_width=150))
    pm.create_panel(PanelSpec("palette", "Blocks", dock="left", width=200, min_width=100))
    pm.create_panel(PanelSpec("work", "Workspace", dock="center", width=300, min_width=200, stretch=True))
    root.update()

    check("ids() sorted by dock, not registration", pm.ids() == ["palette", "work", "code"])
    check("on-screen order follows dock order", screen_order(pm) == ["palette", "work", "code"])
    check("left panel starts at its spec width", pm.frame("palette").winfo_width() == 200)
    check("right panel starts at its spec width", pm.frame("code").winfo_width() == 300)
    check("stretch panel takes the leftover space",
          pm.frame("work").winfo_width() > 600)

    # --- show/hide basics + re-insertion in the right slot ---
    pm.hide("work")
    root.update()
    check("hide removes it from the paned window", not pm.paned.panes() or
          str(pm.frame("work")) not in [str(p) for p in pm.paned.panes()])
    check("hidden panel reports not visible", pm.is_visible("work") is False)
    pm.show("work")
    root.update()
    check("re-shown middle panel returns BETWEEN its neighbours",
          screen_order(pm) == ["palette", "work", "code"])

    pm.hide("palette")
    pm.hide("code")
    root.update()
    check("only center left after hiding both sides", screen_order(pm) == ["work"])
    pm.show("code")      # shown before palette on purpose
    pm.show("palette")
    root.update()
    check("re-show in reverse order still lands in dock order",
          screen_order(pm) == ["palette", "work", "code"])

    # --- idempotence ---
    n = len(events)
    pm.show("palette")
    pm.hide("palette"); pm.hide("palette")
    pm.show("palette")
    root.update()
    check("double show/hide is harmless", screen_order(pm) == ["palette", "work", "code"])
    check("listener fires only on real changes", len(events) - n == 2)
    check("listener got (id, visible) tuples", events[-1] == ("palette", True))

    # --- width memory ---
    pm.set_width("palette", 350)
    root.update()
    check("set_width resizes a shown panel", abs(pm.frame("palette").winfo_width() - 350) <= 2)
    pm.hide("palette")
    root.update()
    pm.show("palette")
    root.update()
    check("hide/show remembers the resized width",
          abs(pm.frame("palette").winfo_width() - 350) <= 2)
    pm.hide("palette")
    pm.set_width("palette", 220)
    pm.show("palette")
    root.update()
    check("set_width while hidden applies on reopen",
          abs(pm.frame("palette").winfo_width() - 220) <= 2)
    pm.set_width("palette", 5)
    check("set_width clamps to min_width", pm.width("palette") >= 100)

    # --- toggle / set_visible ---
    pm.toggle("code"); root.update()
    check("toggle hides a shown panel", pm.is_visible("code") is False)
    pm.toggle("code"); root.update()
    check("toggle shows a hidden panel", pm.is_visible("code") is True)
    pm.set_visible("code", False); pm.set_visible("code", False)
    check("set_visible(False) twice is stable", pm.is_visible("code") is False)
    pm.set_visible("code", True)

    # --- adversarial: hide everything, then bring it back ---
    for pid in pm.ids():
        pm.hide(pid)
    root.update()
    check("hiding every panel leaves an empty layout without error", screen_order(pm) == [])
    for pid in reversed(pm.ids()):
        pm.show(pid)
    root.update()
    check("showing everything back in reverse restores dock order",
          screen_order(pm) == ["palette", "work", "code"])

    # --- errors ---
    check("duplicate id rejected", raises(ValueError, pm.create_panel, PanelSpec("code", "x")))
    check("bad dock rejected", raises(ValueError, pm.create_panel, PanelSpec("z", "z", dock="top")))
    check("failed registration leaves no ghost panel", "z" not in pm.ids())
    check("unknown id -> KeyError (show)", raises(KeyError, pm.show, "nope"))
    check("unknown id -> KeyError (hide)", raises(KeyError, pm.hide, "nope"))
    check("unknown id -> KeyError (is_visible)", raises(KeyError, pm.is_visible, "nope"))
    check("unknown id -> KeyError (set_width)", raises(KeyError, pm.set_width, "nope", 100))

    # --- a second panel in the same dock keeps registration order ---
    pm.create_panel(PanelSpec("plugin", "Plugin", dock="right", width=150, min_width=80))
    root.update()
    check("second right-dock panel sits after the first",
          pm.ids() == ["palette", "work", "code", "plugin"]
          and screen_order(pm) == ["palette", "work", "code", "plugin"])
    pm.hide("code"); pm.show("code"); root.update()
    check("hide/show of first right panel keeps it before its dock-mate",
          screen_order(pm) == ["palette", "work", "code", "plugin"])

    # --- created hidden ---
    pm.create_panel(PanelSpec("later", "Later", dock="left", width=90, min_width=50), visible=False)
    root.update()
    check("visible=False registers without showing", pm.is_visible("later") is False
          and "later" not in screen_order(pm))
    pm.show("later"); root.update()
    check("late-shown left panel lands after the other left panel",
          screen_order(pm)[:3] == ["palette", "later", "work"])

    # --- state round trip (incl. an id that no longer exists) ---
    pm.hide("code")
    pm.set_width("palette", 260)
    root.update()
    state = pm.get_state()
    check("get_state records visibility + width",
          state["code"]["visible"] is False and abs(state["palette"]["width"] - 260) <= 2)
    pm.show("code"); pm.set_width("palette", 180); root.update()
    state["ghost_plugin"] = {"visible": True, "width": 500}
    pm.apply_state(state)
    root.update()
    check("apply_state restores visibility", pm.is_visible("code") is False)
    check("apply_state restores width", abs(pm.frame("palette").winfo_width() - 260) <= 2)
    check("apply_state ignores unknown ids", "ghost_plugin" not in pm.ids())

    # --- a listener that raises must not corrupt the layout ---
    def bad(pid, vis):
        raise RuntimeError("boom")
    pm.add_listener(bad)
    ok = raises(RuntimeError, pm.show, "code")
    root.update()
    check("state stays consistent even if a listener raises",
          pm.is_visible("code") is True and "code" in screen_order(pm) and ok)

    root.destroy()


def integration_tests():
    from ui import BlocklinerUI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800")
    app.update()

    pm = app.panels
    check("app registers the three areas", pm.ids() == ["palette", "workspace", "code"])
    check("app.right_panel is the manager's code frame", app.right_panel is pm.frame("code"))

    # Old layout geometry: palette 280, code 400, 6px gaps, workspace fills.
    check("palette keeps its 280px width", pm.frame("palette").winfo_width() == 280)
    check("code panel keeps its 400px width at Blocks layer", pm.frame("code").winfo_width() == 400)
    p, w, c = (pm.frame(i) for i in ("palette", "workspace", "code"))
    check("6px gap between palette and workspace", w.winfo_x() - (p.winfo_x() + p.winfo_width()) == 6)
    check("6px gap between workspace and code", c.winfo_x() - (w.winfo_x() + w.winfo_width()) == 6)
    check("workspace takes all remaining width",
          abs((c.winfo_x() - 6) - (w.winfo_x() + w.winfo_width())) == 0 and w.winfo_width() > 500)
    check("panels are full height", p.winfo_height() == w.winfo_height() == c.winfo_height() > 300)

    # Layer switching drives the code panel through the manager.
    app.switch_to_file_view(); app.update()
    check("Nodes layer hides the code panel", pm.is_visible("code") is False)
    check("workspace grows into the freed space", pm.frame("workspace").winfo_width() > w.winfo_width() - 1)
    app.switch_to_blocks_view() if hasattr(app, "switch_to_blocks_view") else None
    app.update()

    # Resize the window: side panels keep width, workspace absorbs it.
    if not pm.is_visible("code"):
        app.view_mode = "node"
        app.update_right_panel_visibility()
    app.geometry("1000x700"); app.update()
    check("shrinking the window keeps the palette width", pm.frame("palette").winfo_width() == 280)
    check("shrinking the window keeps the code width", pm.frame("code").winfo_width() == 400)
    app.geometry("1600x900"); app.update()
    check("growing the window keeps the code width", pm.frame("code").winfo_width() == 400)

    # The new capability: hide the palette; workspace gets the room.
    before = pm.frame("workspace").winfo_width()
    pm.hide("palette"); app.update()
    check("hiding the palette gives the workspace its width",
          pm.frame("workspace").winfo_width() >= before + 280)
    pm.show("palette"); app.update()
    check("showing the palette restores 280px and order",
          pm.frame("palette").winfo_width() == 280
          and pm.frame("palette").winfo_x() < pm.frame("workspace").winfo_x())

    # Layer flip while the palette is hidden must not resurrect/hide wrongly.
    pm.hide("palette")
    app.view_mode = "files"; app.update_right_panel_visibility(); app.update()
    app.view_mode = "node"; app.update_right_panel_visibility(); app.update()
    check("layer flips don't touch a user-hidden palette", pm.is_visible("palette") is False)
    check("code panel is back after returning to Blocks layer", pm.is_visible("code") is True)
    pm.show("palette"); app.update()

    # Palette + code still populated (widgets survived being reparented by paned).
    check("palette still has block items", len(app.palette_frame.winfo_children()) > 0)
    check("code_text still readable", isinstance(app.code_text.get("1.0", tk.END), str))

    app.destroy()


if __name__ == "__main__":
    unit_tests()
    integration_tests()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    print("All panel tests passed.")
