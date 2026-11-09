"""Scripted UI test (run under Xvfb): the first-run tour draws a card and an outline inside the
window, walks through the steps, and remembers that it was seen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour
from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(4):
        app.update_idletasks()
        app.update()


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
        check("the layers step outlines the layer bar (4 bars + the card)", len(app._tour_widgets) == 5)
        bar = app.tour_target_widget("layers")
        check("the layer bar is found", bar is not None)

        seen = {app._tour.step["id"]}
        while app.tour_running() and not app._tour.last:
            app._tour_next()
            settle(app)
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
        settle(app)
        check("finishing ends the tour", not app.tour_running() and not app._tour_widgets)
        check("finishing is remembered", app.settings["tour_done"] is True and len(saved) == 1)

        app.start_tour()
        settle(app)
        check("replaying starts at the first step", app.tour_running() and app._tour.first)
        app.end_tour()
        check("closing a replay saves nothing more", len(saved) == 1)

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
