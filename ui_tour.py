"""The first-run tour: an explanation card and a cyan outline drawn INSIDE the main window
(no extra windows, so nothing can be left floating when the window is minimized).
Steps and card placement are in tour.py (pure)."""
import tkinter as tk

import tour
from ui_common import DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL

CARD_WIDTH = 360


class TourMixin:

    def tour_target_widget(self, name):
        """The part of the window a step points at, or None when it isn't on screen."""
        widget = None
        try:
            if name == "layers":
                widget = self.layer_bar
            elif name == "palette":
                widget = self.panels.frame("palette") if self.panels.is_visible("palette") else None
            elif name == "workspace":
                widget = self.workspace_canvas.master
            elif name == "code":
                widget = self.panels.frame("code") if self.panels.is_visible("code") else None
            elif name == "run":
                widget = getattr(self, "run_button", None)
            elif name == "tabs":
                widget = self.tab_bar_frame
            elif name == "menus":
                widget = getattr(self, "_topbar_bar", None)
        except (KeyError, AttributeError, tk.TclError):
            widget = None
        try:
            return widget if widget is not None and widget.winfo_ismapped() and widget.winfo_width() > 4 else None
        except tk.TclError:
            return None

    # ---- starting and finishing ----------------------------------------------------
    def maybe_start_tour(self):
        """Called once after startup: offer the tour to someone who has not seen it."""
        if not self.settings.get("tour_done", False):
            self.start_tour(first_run=True)

    def start_tour(self, first_run=False):
        self.end_tour(remember=False)
        self._tour = tour.Tour()
        self._tour_first_run = first_run
        self._tour_widgets = []
        self.bind("<Escape>", self._tour_escape, add="+")
        self._tour_configure_id = self.bind("<Configure>", self._tour_resized, add="+")
        self._tour_draw()

    def end_tour(self, remember=True):
        """Take the tour down. remember=True records that it was seen (finished or skipped)."""
        for w in getattr(self, "_tour_widgets", []):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._tour_widgets = []
        was_running = getattr(self, "_tour", None) is not None
        self._tour = None
        if was_running and remember and not self.settings.get("tour_done", False):
            self.settings["tour_done"] = True
            self.save_app_settings()

    def tour_running(self):
        return getattr(self, "_tour", None) is not None

    def _tour_escape(self, _event=None):
        if self.tour_running():
            self.end_tour()

    def _tour_resized(self, event):
        if event.widget is self and self.tour_running():
            job = self.__dict__.get("_tour_redraw_job")
            if job is not None:
                self.after_cancel(job)
            self._tour_redraw_job = self.after(120, self._tour_draw)

    # ---- drawing -------------------------------------------------------------------
    def _tour_clear(self):
        for w in getattr(self, "_tour_widgets", []):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._tour_widgets = []

    def _tour_draw(self):
        if not self.tour_running():
            return
        self._tour_redraw_job = None
        self._tour_clear()
        t = self._tour
        step = t.step
        self.update_idletasks()
        target = self.tour_target_widget(step["target"]) if step["target"] else None
        window = (self.winfo_width(), self.winfo_height())
        box = None
        if target is not None:
            box = (target.winfo_rootx() - self.winfo_rootx(), target.winfo_rooty() - self.winfo_rooty(),
                   target.winfo_width(), target.winfo_height())
            for x, y, w, h in tour.outline_rects(box):
                bar = tk.Frame(self, bg="#00e5ff")
                bar.place(x=x, y=y, width=w, height=h)
                self._tour_widgets.append(bar)

        card = tk.Frame(self, bg=DARK_PANEL, highlightthickness=2, highlightbackground="#00e5ff")
        tk.Label(card, text=step["title"], bg=DARK_PANEL, fg="#ffffff", font=("Segoe UI", 12, "bold"),
                 anchor="w").pack(fill=tk.X, padx=14, pady=(12, 4))
        tk.Label(card, text=step["text"], bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 10), anchor="w",
                 justify=tk.LEFT, wraplength=CARD_WIDTH - 28).pack(fill=tk.X, padx=14, pady=(0, 10))
        buttons = tk.Frame(card, bg=DARK_PANEL)
        buttons.pack(fill=tk.X, padx=14, pady=(0, 12))

        def button(text, command, primary=False):
            b = tk.Button(buttons, text=text, command=command, relief=tk.FLAT, cursor="hand2", padx=12, pady=3,
                          font=("Segoe UI", 9, "bold" if primary else "normal"),
                          bg=DARK_ACCENT if primary else "#3a3a3a", fg="#ffffff" if primary else DARK_FG)
            b.pack(side=tk.RIGHT, padx=(6, 0))
            return b

        if t.first and getattr(self, "_tour_first_run", False):
            button("Show me around", self._tour_next, primary=True)
            button("No thanks", self.end_tour)
        else:
            button("Done" if t.last else "Next", self._tour_next, primary=True)
            if not t.first:
                button("Back", self._tour_back)
            if not t.last:
                tk.Button(buttons, text="Skip tour", command=self.end_tour, relief=tk.FLAT, cursor="hand2",
                          font=("Segoe UI", 9), bg=DARK_PANEL, fg="#888888", bd=0).pack(side=tk.LEFT)
                tk.Label(buttons, text=t.progress(), bg=DARK_PANEL, fg="#666666",
                         font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 0))
        card.place(x=0, y=0, width=CARD_WIDTH)
        card.update_idletasks()
        x, y = tour.card_position(box, (CARD_WIDTH, card.winfo_reqheight()), window)
        card.place(x=x, y=y, width=CARD_WIDTH)
        self._tour_widgets.append(card)
        for w in self._tour_widgets:
            w.lift()

    def _tour_next(self):
        if not self.tour_running():
            return
        if not self._tour.next():
            self.end_tour()
            return
        self._tour_draw()

    def _tour_back(self):
        if self.tour_running() and self._tour.back():
            self._tour_draw()
