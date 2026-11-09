"""Scripted UI test (run under Xvfb): the first-run tour draws a card and an outline inside the
window, switches layers, notices when you did what it asked, and remembers that it was seen."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app, seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def on(app, step_id):
    return app.tour_running() and app._tour.step["id"] == step_id


def go_to(app, step_id):
    while app.tour_running() and app._tour.step["id"] != step_id:
        app._tour_next()
        settle(app, 0.4)


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    saved = []
    app.save_app_settings = lambda: saved.append(dict(app.settings))
    try:
        settle(app)
        app.settings["tour_done"] = True
        app.maybe_start_tour()
        check("a tour that was already seen does not start by itself", not app.tour_running())
        check("Help has a Take the tour entry", app.command_registry.get("help.tour") is not None)

        app.settings["tour_done"] = False
        app.maybe_start_tour()
        settle(app)
        check("a new user is offered the tour", app.tour_running() and len(app._tour_widgets) == 1)
        card = app._tour_widgets[0]
        check("the card is inside the window", 0 <= card.winfo_x() and card.winfo_x() + card.winfo_width() <= app.winfo_width())

        app._tour_next()
        settle(app)
        check("the layers step outlines the Blocks button (4 bars + the card)",
              on(app, "layers") and len(app._tour_widgets) == 5)
        check("the Blocks button is what gets outlined", app.tour_target_widget("layer_blocks") is not None)

        # the tour notices that you clicked Blocks and goes on by itself
        app.settings["tour_auto_next"] = True
        app.goto_layer("blocks")
        settle(app, 1.0)
        check("doing what it asked moves on by itself", on(app, "palette"))
        check("the palette step shows the palette (it is on the Blocks layer)", app.tour_target_widget("palette") is not None)
        check("the + of a block is outlined", app.tour_target_widget("palette_add") is not None
              and app.tour_target_widget("palette_add") is not app.tour_target_widget("palette"))

        # with auto-advance off it only says so
        app.settings["tour_auto_next"] = False
        app._tour_draw(settled=True)
        settle(app)
        app.project_blocks.append(("comment", {"text": "x"}))
        settle(app, 1.0)
        check("with auto-advance off it stays and says done", on(app, "palette")
              and "Done" in app._tour_ask_label.cget("text"))
        app._tour_next()
        settle(app, 0.4)
        check("Next then goes on", on(app, "workspace"))

        seen = {"welcome", "layers", "palette", "workspace"}
        while app.tour_running() and not app._tour.last:
            app._tour_next()
            settle(app, 0.5)
            seen.add(app._tour.step["id"])
            cw = app._tour_widgets[-1]
            check(f"step {app._tour.step['id']}: the card fits the window",
                  cw.winfo_x() >= 0 and cw.winfo_y() >= 0
                  and cw.winfo_x() + cw.winfo_width() <= app.winfo_width()
                  and cw.winfo_y() + cw.winfo_height() <= app.winfo_height() + 2)
        check("every step was shown", seen == {s["id"] for s in tour.STEPS})
        app._tour_back()
        settle(app)
        check("Back goes to the step before", app._tour.index == len(tour.STEPS) - 2)
        app._tour_next()
        app._tour_next()                                  # Done on the last step
        settle(app, 0.4)
        check("finishing ends the tour", not app.tour_running() and not app._tour_widgets)
        check("the layer you started on is back", app.view_mode == "files")
        check("finishing is remembered", app.settings["tour_done"] is True)

        count = len(saved)
        app.start_tour()
        settle(app)
        check("replaying starts at the first step", app.tour_running() and app._tour.first)
        app.end_tour()
        check("closing a replay saves nothing more", len(saved) == count)
        check("no grab is left behind", app.grab_current() is None)

        app.settings["tour_done"] = False
        app.maybe_start_tour()
        app.end_tour()
        check("skipping counts as seen", app.settings["tour_done"] is True)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
