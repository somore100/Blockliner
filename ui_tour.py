"""The first-run tour: an explanation card and a cyan outline drawn INSIDE the main window
(no extra windows, so nothing can be left floating when the window is minimized).
Steps and card placement are in tour.py (pure). Some steps switch layer for you and some ask you
to try something (the tour notices when you did and can go on by itself); the layer you started
on is restored at the end."""
import tkinter as tk

import tour
from ui_common import DARK_ACCENT, DARK_FG, DARK_PANEL
from ui_widgets import PaletteBlockItem

CARD_WIDTH = 400
POLL_MS = 300
LAYER_OF_VIEW = {"files": "files", "file": "nodes", "node": "blocks"}


class TourMixin:

    # ---- what a step points at ---------------------------------------------------------
    def _tour_visible(self, widget):
        try:
            return widget if widget is not None and widget.winfo_ismapped() and widget.winfo_width() > 4 else None
        except tk.TclError:
            return None

    def tour_target_widget(self, name):
        """The part of the window a step points at, or None when it isn't on screen."""
        widget = None
        try:
            if name == "layers":
                widget = self.layer_bar
            elif name == "layer_blocks":
                widget = self._layer_buttons["blocks"]
            elif name == "palette":
                widget = self.panels.frame("palette") if self.panels.is_visible("palette") else None
            elif name == "palette_add":
                widget = self._tour_palette_add_button() or (
                    self.panels.frame("palette") if self.panels.is_visible("palette") else None)
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
        return self._tour_visible(widget)

    def _tour_palette_add_button(self):
        """The ＋ of the Print block (or of the first block shown)."""
        items = []

        def walk(w):
            for child in w.winfo_children():
                if isinstance(child, PaletteBlockItem):
                    items.append(child)
                else:
                    walk(child)
        walk(self.palette_frame)
        shown = [i for i in items if self._tour_visible(i.add_button)]
        pick = next((i for i in shown if i.name_label.cget("text") == "Print"), shown[0] if shown else None)
        return pick.add_button if pick else None

    # ---- starting and finishing ----------------------------------------------------------
    def maybe_start_tour(self):
        """Called once after startup: offer the tour to someone who has not seen it."""
        if not self.settings.get("tour_done", False):
            self.start_tour(first_run=True)

    def start_tour(self, first_run=False):
        self.end_tour(remember=False)
        self._tour = tour.Tour()
        self._tour_first_run = first_run
        self._tour_widgets = []
        self._tour_start_layer = LAYER_OF_VIEW.get(self.view_mode)
        self._tour_baseline = 0
        self.bind("<Escape>", self._tour_escape, add="+")
        self.bind("<Configure>", self._tour_resized, add="+")
        self._tour_draw()

    def end_tour(self, remember=True):
        """Take the tour down and put the window back as it was. remember=True records
        that it was seen (finished or skipped)."""
        self._tour_clear()
        for job in ("_tour_poll_job", "_tour_redraw_job"):
            pending = self.__dict__.get(job)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
                self.__dict__[job] = None
        was_running = getattr(self, "_tour", None) is not None
        self._tour = None
        if not was_running:
            return
        try:                                              # never leave a grab behind: it would block every click
            grabbed = self.grab_current()
            if grabbed is not None:
                grabbed.grab_release()
        except tk.TclError:
            pass
        back = getattr(self, "_tour_start_layer", None)
        if remember and back and LAYER_OF_VIEW.get(self.view_mode) != back:
            self.goto_layer(back)
        if remember and not self.settings.get("tour_done", False):
            self.settings["tour_done"] = True
            self.save_app_settings()
        self.focus_set()

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
            self._tour_redraw_job = self.after(150, lambda: self._tour_draw(settled=True))

    # ---- drawing -------------------------------------------------------------------------
    def _tour_clear(self):
        for w in getattr(self, "_tour_widgets", []):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._tour_widgets = []

    def _tour_show_layer(self, layer):
        """Switch to the layer a step wants; True when something had to change."""
        if layer and LAYER_OF_VIEW.get(self.view_mode) != layer:
            self.goto_layer(layer)
            return True
        return False

    def _tour_draw(self, settled=False):
        if not self.tour_running():
            return
        self._tour_redraw_job = None
        self._tour_clear()
        step = self._tour.step
        if not settled and self._tour_show_layer(step.get("layer")):
            self.update_idletasks()
            self._tour_redraw_job = self.after(150, lambda: self._tour_draw(settled=True))     # let the new layer lay out
            return
        self.update_idletasks()
        t = self._tour
        where = step.get("where") or step["target"]
        target = self.tour_target_widget(where) if where else None
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
                 anchor="w").pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(card, text=step["text"], bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 10), anchor="w",
                 justify=tk.LEFT, wraplength=CARD_WIDTH - 44).pack(fill=tk.X, padx=16, pady=(0, 10))
        self._tour_ask_label = None
        if "ask" in step:
            self._tour_ask_label = tk.Label(card, text="\U0001F449 " + step["ask"], bg=DARK_PANEL, fg="#00e5ff",
                                            font=("Segoe UI", 10, "bold"), anchor="w", justify=tk.LEFT,
                                            wraplength=CARD_WIDTH - 44)
            self._tour_ask_label.pack(fill=tk.X, padx=16, pady=(0, 6))
            auto = tk.BooleanVar(value=bool(self.settings.get("tour_auto_next", True)))

            def remember_auto():
                self.settings["tour_auto_next"] = bool(auto.get())
                self.save_app_settings()
            tk.Checkbutton(card, text="Go on by itself when I've done it", variable=auto, command=remember_auto,
                           bg=DARK_PANEL, fg=DARK_FG, selectcolor="#1e1e1e", activebackground=DARK_PANEL,
                           activeforeground=DARK_FG, font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=12, pady=(0, 8))
        buttons = tk.Frame(card, bg=DARK_PANEL)
        buttons.pack(fill=tk.X, padx=16, pady=(2, 16))

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
        height = card.winfo_reqheight() + 4
        x, y = tour.card_position(box, (CARD_WIDTH, height), window)
        card.place(x=x, y=y, width=CARD_WIDTH, height=height)
        self._tour_widgets.append(card)
        for w in self._tour_widgets:
            w.lift()
        self._tour_watch_step()

    # ---- steps that ask you to try something --------------------------------------------
    def _tour_watch_step(self):
        job = self.__dict__.get("_tour_poll_job")
        if job is not None:
            self.after_cancel(job)
            self._tour_poll_job = None
        if "done" in self._tour.step:
            self._tour_baseline = len(self.project_blocks) if self.view_mode == "node" else 0
            self._tour_poll_job = self.after(POLL_MS, self._tour_poll)

    def _tour_condition(self, key):
        if key == "layer_blocks":
            return self.view_mode == "node"
        if key == "block_added":
            return self.view_mode == "node" and len(self.project_blocks) > self._tour_baseline
        return False

    def _tour_poll(self):
        self._tour_poll_job = None
        if not self.tour_running() or "done" not in self._tour.step:
            return
        if self._tour_condition(self._tour.step["done"]):
            if self.settings.get("tour_auto_next", True):
                self._tour_next()
            elif self._tour_ask_label is not None:
                self._tour_ask_label.config(text="✅ Done! Press Next.", fg="#6bd48a")
            return
        self._tour_poll_job = self.after(POLL_MS, self._tour_poll)

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
