"""The UI designer as a component: a widget palette, an outline of the widget
tree, a paper to arrange widgets on, and a properties panel.

It knows two things outside itself and nothing else:
  host  the window it lives in: frame, after/after_idle, bell, winfo_rgb,
        view_width(), refresh(), showing()
  port  the document it edits (designer_port.UIDocumentPort)
Pure logic is in ui_designer_model.py; the tree in ui_tree.py."""
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

import canvas_view
import paper_view
import ui_designer_model as dm
import ui_paper
from ui_common import BLOCK_BG, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL

NONE_LABEL = "(none)"
NEW_LABEL = "+ New function…"
OPEN_WINDOW = "Open window: "
TOOLBAR_ONE_ROW = 800        # narrower than this, the device buttons get a row of their own
PAPER_MARGIN = 14
PALETTE_WIDTH = 170
PROPS_WIDTH = 290
PAPER_BG = "#f4f4f4"
PAPER_FG = "#222222"
FONT_FAMILIES = ("Helvetica", "Arial", "Times", "Courier", "Segoe UI", "DejaVu Sans", "Verdana", "Georgia")
DRAG_START = 3          # px the pointer moves before a press becomes a drag
HANDLE_CURSORS = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow", "e": "sb_h_double_arrow",
                  "w": "sb_h_double_arrow", "nw": "top_left_corner", "ne": "top_right_corner",
                  "sw": "bottom_left_corner", "se": "bottom_right_corner"}


class UIDesignerEditor:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.state = {}

    def _dz(self):
        return self.state

    def on_resized(self, width):
        """The view changed width: relayout the toolbar if it crossed the one-row limit."""
        if "wide" in self.state and self.state["wide"] != (width >= TOOLBAR_ONE_ROW):
            self.host.after_idle(lambda: self._dz_update(code=False))

    def render(self):
        self.render_designer()

    def reset(self):
        """Forget the cached tree and selection (the node was detached or taken back)."""
        self.state.clear()

    def _dz_tree(self):
        """The document's live UITree (kept between refreshes so undo survives)."""
        st = self.state
        cached = st.get("tree")
        if st.get("node_id") != self.port.key() or cached is None or cached.to_dict() != self.port.stored():
            st.clear()
            st.update(node_id=self.port.key(), tree=self.port.load_tree(), sel=None)
            self.port.store_tree(st["tree"])        # same normalised form as the cache
        return st["tree"]

    # ---- rendering ------------------------------------------------------
    def render_designer(self):
        pack = self.port.pack()
        tree = self._dz_tree()
        st = self._dz()
        if st.get("sel") and tree.find(st["sel"]) is None:
            st["sel"] = None
        self._dz_style()

        frame = self.host.frame
        frame.update_idletasks()
        if not getattr(self, "_frame_bound", False):
            frame.bind("<Configure>", lambda ev: self.on_resized(ev.width) if ev.widget is frame else None, add="+")
            self._frame_bound = True
        st["shown"] = (self.port.key(), st.get("hide_pal"), st.get("hide_props"))
        outer = tk.Frame(self.host.frame, bg=DARK_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self._dz_root = outer
        self._dz_bar = tk.Frame(outer, bg=DARK_BG)
        self._dz_bar.pack(fill=tk.X)
        st.pop("bar_key", None)
        self._dz_toolbar(self._dz_bar, tree, pack)
        body = tk.Frame(outer, bg=DARK_BG)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        if not st.get("hide_pal"):
            self._dz_palette(body, tree, pack)
        centre = tk.Frame(body, bg=DARK_BG)
        centre.grid(row=0, column=1, sticky="nsew")
        self._dz_out_box = tk.Frame(centre, bg=DARK_PANEL)
        self._dz_out_box.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))    # packed first so it keeps its room
        self._dz_outline(self._dz_out_box, tree, pack)
        self._dz_paper(centre, tree, pack)
        if not st.get("hide_props"):
            self._dz_props_scroller(body)
            self._dz_render_props(tree, pack)

    def _dz_props_scroller(self, body):
        """The settings panel scrolls (a widget can have many settings);
        the wheel reaches it through ui.py _install_wheel."""
        outer = tk.Frame(body, bg=DARK_PANEL, width=PROPS_WIDTH)
        outer.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        outer.pack_propagate(False)
        canvas = tk.Canvas(outer, bg=DARK_PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=DARK_PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw", tags="inner")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure("inner", width=e.width))

        def yscroll(first, last):
            bar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                bar.pack_forget()
            elif not bar.winfo_ismapped():
                bar.pack(side=tk.RIGHT, fill=tk.Y, before=canvas)
        canvas.configure(yscrollcommand=yscroll)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._dz_props_frame, self._dz_props_canvas = inner, canvas

    def _dz_update(self, code=True):
        """Bring the shown designer up to date without rebuilding it (a full
        refresh_workspace() flashes). code=False: only the selection or the
        size changed, the tree did not."""
        root = getattr(self, "_dz_root", None)
        if not self.host.showing() or root is None or not root.winfo_exists():
            self.host.refresh()
            return
        pack = self.port.pack()
        tree = self._dz_tree()
        st = self._dz()
        if st.get("shown") != (self.port.key(), st.get("hide_pal"), st.get("hide_props")):
            self.host.refresh()                    # another node, or the cache was reset
            return
        if st.get("sel") and tree.find(st["sel"]) is None:
            st["sel"] = None
        if code:
            self.port.regenerate()
        self._dz_toolbar(self._dz_bar, tree, pack)
        if code or self._dz_out is None:
            self._dz_rebuild_outline(tree, pack)
        else:
            sel = st.get("sel")
            if sel and self._dz_out.exists(sel):
                self._dz_out.selection_set(sel)
                self._dz_out.see(sel)
            elif self._dz_out.selection():
                self._dz_out.selection_remove(*self._dz_out.selection())
        self._dz_draw_paper(tree, pack)
        if not st.get("hide_props"):
            self._dz_render_props(tree, pack)

    def _dz_rebuild_outline(self, tree, pack):
        for w in self._dz_out_box.winfo_children():
            w.destroy()
        self._dz_outline(self._dz_out_box, tree, pack)

    def _dz_style(self):
        style = ttk.Style()
        style.configure("Designer.Treeview", background=DARK_BG, fieldbackground=DARK_BG,
                        foreground=DARK_FG, borderwidth=0, rowheight=24)
        style.map("Designer.Treeview", background=[("selected", DARK_ACCENT)],
                  foreground=[("selected", "#ffffff")])

    def _dz_button(self, parent, text, command, state=tk.NORMAL):
        return tk.Button(parent, text=text, command=command, state=state, bg="#3a3a3a", fg=DARK_FG,
                         relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), padx=8)

    def _dz_toolbar(self, parent, tree, pack):
        """Undo/redo, the device the paper imitates, and the code switch.
        Widget actions (duplicate, move, remove) live in the settings panel.
        On a narrow workspace the device buttons go on a second row."""
        st = self._dz()
        wide = self.host.view_width() >= TOOLBAR_ONE_ROW
        key = (wide, tree.can_undo, tree.can_redo, self._dz_device(tree), st.get("hide_pal"), st.get("hide_props"))
        if st.get("bar_key") == key:
            return
        st["bar_key"], st["wide"] = key, wide
        for w in parent.winfo_children():
            w.destroy()
        bar = tk.Frame(parent, bg=DARK_BG)
        bar.pack(fill=tk.X, pady=(0, 6))
        if st["wide"]:
            dev_bar = bar
        else:
            dev_bar = tk.Frame(parent, bg=DARK_BG)
            dev_bar.pack(fill=tk.X, pady=(0, 6))
        self._dz_button(bar, "↶ Undo", self._dz_undo, tk.NORMAL if tree.can_undo else tk.DISABLED).pack(side=tk.LEFT, padx=2)
        self._dz_button(bar, "↷ Redo", self._dz_redo, tk.NORMAL if tree.can_redo else tk.DISABLED).pack(side=tk.LEFT, padx=2)
        tk.Frame(bar, width=14, bg=DARK_BG).pack(side=tk.LEFT)
        for key, text in (("hide_pal", "Widgets"), ("hide_props", "Settings")):
            on = not st.get(key)
            tk.Button(bar, text=text, command=lambda k=key: self._dz_toggle_side(k), relief=tk.FLAT, cursor="hand2",
                      bg=DARK_ACCENT if on else "#3a3a3a", fg="#ffffff" if on else DARK_FG,
                      font=("Segoe UI", 9), padx=8).pack(side=tk.LEFT, padx=1)
        if st["wide"]:
            tk.Frame(bar, width=14, bg=DARK_BG).pack(side=tk.LEFT)
        tk.Label(dev_bar, text="Device", bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        device = self._dz_device(tree)
        for key, (label, w, h) in ui_paper.DEVICES.items():
            on = key == device
            tk.Button(dev_bar, text=label, command=lambda k=key: self._dz_set_device(k), relief=tk.FLAT, cursor="hand2",
                      bg=DARK_ACCENT if on else "#3a3a3a", fg="#ffffff" if on else DARK_FG,
                      font=("Segoe UI", 9), padx=8).pack(side=tk.LEFT, padx=1)
        self._dz_button(bar, "</> Code…", self._dz_detach).pack(side=tk.RIGHT, padx=2)
        self._dz_button(bar, "\u26a1 Behaviour", self.port.show_behaviour).pack(side=tk.RIGHT, padx=2)
        self._dz_button(bar, "▶ Preview", self._dz_preview).pack(side=tk.RIGHT, padx=2)

    def _dz_toggle_side(self, key):
        st = self._dz()
        st[key] = not st.get(key)
        self.host.refresh()

    def _dz_side_header(self, parent, text, key):
        """Title row of a side panel with a close button."""
        row = tk.Frame(parent, bg=DARK_PANEL)
        row.pack(fill=tk.X)
        tk.Label(row, text=text, bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(side=tk.LEFT, padx=8, pady=(6, 2))
        close = tk.Label(row, text="\u2715", bg=DARK_PANEL, fg="#888888", cursor="hand2", padx=6)
        close.pack(side=tk.RIGHT, pady=(4, 0))
        close.bind("<Button-1>", lambda e: self._dz_toggle_side(key))

    def _dz_device(self, tree):
        key = (tree.root.get("design") or {}).get("device")
        return key if key in ui_paper.DEVICES else ui_paper.DEFAULT_DEVICE

    def _dz_set_device(self, key):
        root_id = self._dz_tree_now().root["id"]
        self._dz()["view"] = None                       # a different paper: fit it again
        self._dz_apply(lambda t: t.set_design(root_id, device=key))

    def _dz_tree_now(self):
        return self._dz_tree()

    def _dz_palette(self, body, tree, pack):
        """Widget types; click one to add it (inside the selected container,
        else next to the selected widget, else into the window)."""
        frame = tk.Frame(body, bg=DARK_PANEL, width=PALETTE_WIDTH)
        frame.grid(row=0, column=0, sticky="ns", padx=(0, 6))
        frame.grid_propagate(False)
        self._dz_side_header(frame, "Widgets  (click to add)", "hide_pal")
        hint = tk.Label(frame, text=pack.description or "", bg=DARK_PANEL, fg="#9a9a9a", font=("Segoe UI", 9),
                        wraplength=PALETTE_WIDTH - 20, justify=tk.LEFT, anchor="nw", height=5)
        hint.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        pal = ttk.Treeview(frame, show="tree", selectmode="none", style="Designer.Treeview")
        pal.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        for category, widgets in pack.palette():
            cat = pal.insert("", "end", iid=f"c:{category}", text=category, open=True)
            for w in widgets:
                pal.insert(cat, "end", iid=f"w:{w['type']}", text=f"{w['icon']} {w['label']}".strip())
        pal.bind("<ButtonRelease-1>", self._dz_palette_click)

        def describe(event):
            row = pal.identify_row(event.y)
            w = pack.widget(row[2:]) if row.startswith("w:") else None
            hint.configure(text=(f"{w['label']}: {w['description']}" if w and w["description"] else
                                 (pack.description or "")))
        pal.bind("<Motion>", describe)
        pal.bind("<Leave>", lambda e: hint.configure(text=pack.description or ""))
        self._dz_pal, self._dz_pal_hint = pal, hint

    def _dz_palette_click(self, event):
        row = self._dz_pal.identify_row(event.y)
        if row.startswith("w:"):
            self._dz_add_type(row[2:])

    # ---- the paper -------------------------------------------------------
    def _dz_paper(self, parent, tree, pack):
        """Drawn on every resize, shrunk (never grown) to fit the space."""
        canvas = tk.Canvas(parent, bg="#2a2a2e", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self._dz_canvas, self._dz_boxes, self._dz_origin, self._dz_scale = canvas, [], (0, 0), 1.0
        canvas.bind("<Configure>", lambda e: self._dz_draw_paper(tree, pack))
        canvas.bind("<Button-1>", self._dz_paper_press)
        canvas.bind("<B1-Motion>", self._dz_paper_drag)
        canvas.bind("<ButtonRelease-1>", self._dz_paper_release)
        canvas.bind("<Motion>", self._dz_paper_hover)
        # camera: wheel zooms, middle button (or Space + left) drags the view
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind(seq, self._dz_paper_wheel)
        canvas.bind("<ButtonPress-2>", self._dz_pan_press)
        canvas.bind("<B2-Motion>", self._dz_pan_motion)
        canvas.bind("<ButtonRelease-2>", self._dz_pan_release)
        canvas.bind("<Enter>", self._dz_paper_enter)
        # typing straight onto the paper: double-click, or Enter / F2 on the selected widget
        canvas.bind("<Double-Button-1>", self._dz_paper_double)
        canvas.bind("<Return>", lambda e: self._dz_edit_selected())
        canvas.bind("<F2>", lambda e: self._dz_edit_selected())
        canvas.bind("<KeyPress-space>", lambda e: self._dz_set_space(True))
        canvas.bind("<KeyRelease-space>", lambda e: self._dz_set_space(False))
        self._dz_drag = None
        self._dz_pan = None
        self._dz_space = False
        self._dz_inline = None
        self._dz_zoom_controls(canvas)

    def _dz_zoom_controls(self, canvas):
        """A small - 100% + Fit strip in the paper's bottom-right corner."""
        bar = tk.Frame(canvas, bg=DARK_PANEL, highlightthickness=1, highlightbackground=DARK_BORDER)
        bar.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

        def btn(text, cmd, width=None):
            b = tk.Label(bar, text=text, bg=DARK_PANEL, fg=DARK_FG, cursor="hand2", padx=7, pady=2,
                         font=("Segoe UI", 9), width=width)
            b.pack(side=tk.LEFT)
            b.bind("<Button-1>", lambda e: (cmd(), "break")[1])
            return b
        btn("\u2212", lambda: self._dz_zoom_step(1, paper_view.BUTTON_STEP, centre=True))
        self._dz_zoom_label = btn("100%", self._dz_zoom_reset, width=5)
        btn("+", lambda: self._dz_zoom_step(-1, paper_view.BUTTON_STEP, centre=True))
        btn("Fit", self._dz_fit)
        self._dz_zoom_bar = bar

    def _dz_draw_paper(self, tree, pack):
        canvas = self._dz_canvas
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        pw, ph = ui_paper.device_size(self._dz_device(tree))
        view = self._dz().get("view")
        if view is None:
            s, ox, oy = paper_view.fit((cw, ch), (pw, ph), PAPER_MARGIN)
        else:
            s = paper_view.clamp_scale(view["s"])
            ox, oy = paper_view.clamp_origin((view["ox"], view["oy"]), s, (pw, ph), (cw, ch))
        self._dz_paper_size = (pw, ph)
        label = getattr(self, "_dz_zoom_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=paper_view.percent(s))
        self._dz_paper_obj = ui_paper.Paper(tree, pack)
        layout = self._dz_paper_obj.boxes(pw, ph)
        self._dz_boxes, self._dz_origin, self._dz_scale = layout, (ox, oy), s
        sel = self._dz().get("sel")
        canvas.delete("all")
        canvas.create_rectangle(ox + 3, oy + 3, ox + pw * s + 3, oy + ph * s + 3, fill="#1a1a1c", outline="")
        for b in layout:
            self._dz_draw_box(canvas, tree, pack, b, ox, oy, s, selected=(b["id"] == sel))
        self._dz_place_inline()

    def _dz_draw_box(self, canvas, tree, pack, b, ox, oy, s, selected):
        node = tree.find(b["id"])
        x0, y0 = ox + b["x"] * s, oy + b["y"] * s
        x1, y1 = x0 + b["w"] * s, y0 + b["h"] * s
        kind, text = b["type"], str((node["props"].get("text") or "") if node else "")
        props = node["props"] if node else {}
        family, size, styles = ui_paper.parse_font(props.get("font"))
        font = (family, max(5, round(size * s)), *[st for st in styles if st in ("bold", "italic")])
        fg = self._dz_colour(props.get("foreground"), PAPER_FG)
        bg = self._dz_colour(props.get("background"), None)
        is_root = b["depth"] == 0
        if is_root:
            canvas.create_rectangle(x0, y0, x1, y1, fill=PAPER_BG, outline="#888888")
            canvas.create_rectangle(x0, y0 - 0, x1, y0 + 1, fill="#888888", outline="")
            title = str(node["props"].get("title") or "") if node else ""
            if title:
                canvas.create_text(x0 + 6, y0 + 4, text=title, anchor="nw", fill="#999999", font=("Segoe UI", 8))
        elif kind == "label":
            if bg:
                canvas.create_rectangle(x0, y0, x1, y1, fill=bg, outline="")
            canvas.create_text(x0, (y0 + y1) / 2, text=text or "Label", anchor="w", fill=fg, font=font)
        elif kind == "button":
            canvas.create_rectangle(x0, y0, x1, y1, fill=bg or "#e1e1e1", outline="#9a9a9a")
            canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text or "Button", fill=fg, font=font)
        elif kind == "checkbutton":
            if bg:
                canvas.create_rectangle(x0, y0, x1, y1, fill=bg, outline="")
            canvas.create_rectangle(x0, (y0 + y1) / 2 - 6, x0 + 12, (y0 + y1) / 2 + 6, fill="#ffffff", outline="#777777")
            canvas.create_text(x0 + 18, (y0 + y1) / 2, text=text or "Check", anchor="w", fill=fg, font=font)
        elif kind == "frame":
            canvas.create_rectangle(x0, y0, x1, y1, fill="", outline="#b5b5b5", dash=(3, 3))
        else:                                    # entry, text, listbox, combobox and unknown types
            canvas.create_rectangle(x0, y0, x1, y1, fill=bg or "#ffffff", outline="#9a9a9a")
            if props.get("font") or props.get("foreground"):
                canvas.create_text(x0 + 4, (y0 + y1) / 2 if kind in ("entry", "combobox") else y0 + 4,
                                   text="Abc", anchor="w" if kind in ("entry", "combobox") else "nw", fill=fg, font=font)
            label = {"combobox": "▾", "listbox": "≡"}.get(kind, "")
            if label:
                canvas.create_text(x1 - 8, (y0 + y1) / 2, text=label, fill="#666666")
            if kind not in ("entry", "text", "listbox", "combobox") and b["w"] * s > 40:
                canvas.create_text(x0 + 4, (y0 + y1) / 2, text=kind, anchor="w", fill="#aaaaaa", font=("Segoe UI", 8))
        if selected:
            canvas.create_rectangle(x0 - 1, y0 - 1, x1 + 1, y1 + 1, outline=DARK_ACCENT, width=2)
            edges = dm.resize_edges(tree, pack, b["id"])
            xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
            for hx, hy, need in ((x0, y0, "nw"), (xm, y0, "n"), (x1, y0, "ne"), (x1, ym, "e"),
                                 (x1, y1, "se"), (xm, y1, "s"), (x0, y1, "sw"), (x0, ym, "w")):
                if all(c in edges for c in need):
                    canvas.create_rectangle(hx - 3, hy - 3, hx + 3, hy + 3, fill=DARK_ACCENT, outline="#ffffff")

    def _dz_colour(self, value, fallback):
        """A colour Tk can draw, else fallback (a typo must not break the paper)."""
        if not value:
            return fallback
        try:
            self.host.winfo_rgb(value)
            return value
        except tk.TclError:
            return fallback

    def _dz_paper_point(self, event):
        ox, oy = self._dz_origin
        return (event.x - ox) / self._dz_scale, (event.y - oy) / self._dz_scale

    def _dz_box(self, widget_id):
        return next((b for b in self._dz_boxes if b["id"] == widget_id), None) if widget_id else None

    def _dz_handle_under(self, tree, pack, px, py):
        """Resize handle of the selected widget under the paper point, or ''."""
        sel = self._dz().get("sel")
        box = self._dz_box(sel)
        if box is None:
            return ""
        return dm.handle_at(box, dm.resize_edges(tree, pack, sel), px, py, dm.HANDLE / self._dz_scale)

    def _dz_paper_press(self, event):
        """Press on a handle of the selected widget: resize it. Press on a
        widget: select it, and dragging it moves it (grid: to another cell)."""
        self._dz_close_inline(commit=True)                  # clicking away keeps what was typed
        tree, pack = self._dz_tree_now(), self.port.pack()
        px, py = self._dz_paper_point(event)
        st = self._dz()
        self._dz_drag = None
        if self._dz_space:                                  # Space held: the camera, not the widgets
            self._dz_pan_press(event)
            return
        handle = self._dz_handle_under(tree, pack, px, py)
        if handle:
            self._dz_drag = {"id": st["sel"], "mode": handle, "start": (px, py), "box": self._dz_box(st["sel"]), "rect": None}
            return
        hit = ui_paper.hit_test(self._dz_boxes, px, py)
        if hit is None:                                     # empty space: drag moves the view, a plain click deselects
            self._dz_pan_press(event)
            self._dz_pan["deselect"] = True
            return
        if hit != st.get("sel"):
            st["sel"] = hit
            self._dz_update(code=False)
        if hit and dm.can_move(tree, hit):
            self._dz_drag = {"id": hit, "mode": "move", "start": (px, py), "box": self._dz_box(hit), "rect": None}

    def _dz_paper_drag(self, event):
        """Outline where the widget would go; the tree changes on release."""
        if self._dz_pan is not None:
            self._dz_pan_motion(event)
            return
        d = self._dz_drag
        if d is None or d["box"] is None:
            return
        px, py = self._dz_paper_point(event)
        dx, dy = px - d["start"][0], py - d["start"][1]
        s = self._dz_scale
        if d["rect"] is None and abs(dx) * s < DRAG_START and abs(dy) * s < DRAG_START:
            return
        b = d["box"]
        if d["mode"] == "move":
            d["rect"] = (b["x"] + dx, b["y"] + dy, b["w"], b["h"])
        else:
            d["rect"] = dm.resize_box(b, d["mode"], dx, dy)
        x, y, w, h = d["rect"]
        ox, oy = self._dz_origin
        canvas = self._dz_canvas
        canvas.delete("ghost")
        canvas.create_rectangle(ox + x * s, oy + y * s, ox + (x + w) * s, oy + (y + h) * s,
                                outline=DARK_ACCENT, width=2, dash=(4, 2), tags="ghost")

    def _dz_paper_release(self, event):
        if self._dz_pan is not None:
            self._dz_pan_release(event)
            return
        d, self._dz_drag = self._dz_drag, None
        if d is None or d["rect"] is None:
            return
        self._dz_canvas.delete("ghost")
        tree, pack = self._dz_tree_now(), self.port.pack()
        if d["mode"] == "move":
            changes = dm.move_changes(tree, self._dz_paper_obj, self._dz_boxes, d["id"], *d["rect"], pack=pack)
        else:
            changes = dm.resize_changes(tree, pack, self._dz_boxes, d["id"], *d["rect"])
        if changes:
            self._dz_apply(lambda t: t.edit_many(changes))

    def _dz_paper_hover(self, event):
        """Resize cursor over a handle, move cursor over the selected widget."""
        if self._dz_drag is not None or self._dz_pan is not None:
            return
        tree, pack = self._dz_tree_now(), self.port.pack()
        px, py = self._dz_paper_point(event)
        handle = self._dz_handle_under(tree, pack, px, py)
        sel = self._dz().get("sel")
        if self._dz_space:
            cursor = "hand2"
        elif handle:
            cursor = HANDLE_CURSORS.get(handle, "fleur")
        elif sel and ui_paper.hit_test(self._dz_boxes, px, py) == sel and dm.can_move(tree, sel):
            cursor = "fleur"
        else:
            cursor = ""
        if str(self._dz_canvas.cget("cursor")) != cursor:
            self._dz_canvas.configure(cursor=cursor)

    # ---- typing straight onto the paper ----------------------------------------
    def _dz_paper_double(self, event):
        """Double-click a widget to type its text in place, like a text box in a
        slide. On the window itself only the title strip does it."""
        px, py = self._dz_paper_point(event)
        hit = ui_paper.hit_test(self._dz_boxes, px, py)
        box = self._dz_box(hit)
        if box is None or (box["depth"] == 0 and py - box["y"] > 24):
            return
        st = self._dz()
        if st.get("sel") != hit:
            st["sel"] = hit
            self._dz_update(code=False)
        self._dz_edit_text(hit)

    def _dz_edit_selected(self):
        sel = self._dz().get("sel")
        if sel:
            self._dz_edit_text(sel)
        return "break"

    def _dz_edit_text(self, wid):
        """A text box over the widget; Enter or clicking away keeps the text,
        Esc drops it. False when the widget has no text of its own."""
        tree, pack = self._dz_tree_now(), self.port.pack()
        node = tree.find(wid)
        key = dm.inline_prop(pack, node["type"]) if node else None
        if key is None or self._dz_box(wid) is None:
            return False
        self._dz_close_inline(commit=True)
        family, size, styles = ui_paper.parse_font(node["props"].get("font"))
        font = (family, max(7, round(size * self._dz_scale)), *[st for st in styles if st in ("bold", "italic")])
        entry = tk.Entry(self._dz_canvas, font=font, relief=tk.SOLID, bd=1, bg="#ffffff", fg="#111111",
                         insertbackground="#111111", highlightthickness=2, highlightcolor=DARK_ACCENT,
                         highlightbackground=DARK_ACCENT)
        entry.insert(0, str(node["props"].get(key) or ""))
        entry.select_range(0, tk.END)
        entry.bind("<Return>", lambda e: (self._dz_close_inline(True), "break")[1])
        entry.bind("<Escape>", lambda e: (self._dz_close_inline(False), "break")[1])
        entry.bind("<FocusOut>", lambda e: self._dz_close_inline(True))
        self._dz_inline = {"id": wid, "key": key, "entry": entry}
        self._dz_place_inline()
        entry.focus_set()
        return True

    def _dz_place_inline(self):
        """(Re)put the text box over its widget; called after every redraw so
        zooming and panning carry it along."""
        ed = getattr(self, "_dz_inline", None)
        if not ed:
            return
        box = self._dz_box(ed["id"])
        if box is None:
            self._dz_close_inline(commit=False)
            return
        s, (ox, oy) = self._dz_scale, self._dz_origin
        x, y = ox + box["x"] * s, oy + box["y"] * s
        w, h = max(box["w"] * s, 110), max(box["h"] * s, 24)
        if box["depth"] == 0:                                # the window's title sits in its top strip
            x, y, w, h = x + 6, y + 2, 220, 24
        self._dz_canvas.delete("inline")
        self._dz_canvas.create_window(x, y, window=ed["entry"], anchor="nw", width=w, height=h, tags="inline")

    def _dz_close_inline(self, commit):
        ed, self._dz_inline = getattr(self, "_dz_inline", None), None      # cleared first: destroying fires FocusOut
        if not ed:
            return
        text = ed["entry"].get()
        try:
            ed["entry"].destroy()
            self._dz_canvas.delete("inline")
            self._dz_canvas.focus_set()
        except tk.TclError:
            pass
        if commit:
            node = self._dz_tree_now().find(ed["id"])
            if node is not None and text != str(node["props"].get(ed["key"]) or ""):
                self._dz_apply(lambda t: t.set_prop(ed["id"], ed["key"], text))

    # ---- the camera: zoom and pan --------------------------------------------
    def _dz_set_view(self, scale, origin):
        """Take the camera off 'fit' and put it here; redraw."""
        self._dz()["view"] = {"s": paper_view.clamp_scale(scale), "ox": origin[0], "oy": origin[1]}
        self._dz_draw_paper(self._dz_tree_now(), self.port.pack())

    def _dz_paper_enter(self, _event):
        """Take the keyboard so Space works, but never from a field being typed in."""
        try:
            current = self._dz_canvas.focus_get()
        except (KeyError, tk.TclError):
            current = None
        if current is None or current.winfo_class() not in ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"):
            self._dz_canvas.focus_set()

    def _dz_zoom_reset(self):
        """Back to 100%, around the middle of the view."""
        canvas = self._dz_canvas
        centre = (canvas.winfo_width() / 2, canvas.winfo_height() / 2)
        self._dz_set_view(1.0, paper_view.zoom_about(self._dz_scale, self._dz_origin, centre, 1.0))

    def _dz_fit(self):
        self._dz()["view"] = None
        self._dz_draw_paper(self._dz_tree_now(), self.port.pack())

    def _dz_zoom_step(self, step, factor, anchor=None, centre=False):
        """step < 0 zooms in, step > 0 out. The anchor (canvas px) stays still."""
        canvas = self._dz_canvas
        if centre or anchor is None:
            anchor = (canvas.winfo_width() / 2, canvas.winfo_height() / 2)
        old = self._dz_scale
        new = canvas_view.zoom_after_wheel(old, step, factor)
        new = max(paper_view.ZOOM_MIN, min(paper_view.ZOOM_MAX, new))
        if abs(new - old) < 1e-9:
            return
        self._dz_set_view(new, paper_view.zoom_about(old, self._dz_origin, anchor, new))

    def _dz_zoom_speed(self):
        read = getattr(self.host, "setting", None)
        return canvas_view.zoom_factor({"zoom_speed": read("zoom_speed", None)} if read else {})

    def _dz_paper_wheel(self, event):
        """The wheel zooms around the pointer (the same speed setting as the Nodes canvas)."""
        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        elif getattr(event, "delta", 0):
            step = -1 if event.delta > 0 else 1
        else:
            return "break"
        self._dz_zoom_step(step, self._dz_zoom_speed(), anchor=(event.x, event.y))
        return "break"

    def _dz_set_space(self, on):
        self._dz_space = on
        if self._dz_pan is None:
            self._dz_canvas.configure(cursor="hand2" if on else "")

    def _dz_pan_press(self, event):
        self._dz_pan = {"start": (event.x, event.y), "origin": self._dz_origin, "scale": self._dz_scale,
                        "moved": False, "deselect": False}
        self._dz_canvas.configure(cursor="fleur")

    def _dz_pan_motion(self, event):
        p = self._dz_pan
        if p is None:
            return
        dx, dy = event.x - p["start"][0], event.y - p["start"][1]
        if not p["moved"] and abs(dx) < DRAG_START and abs(dy) < DRAG_START:
            return
        p["moved"] = True
        canvas = self._dz_canvas
        origin = paper_view.clamp_origin((p["origin"][0] + dx, p["origin"][1] + dy), p["scale"],
                                         self._dz_paper_size, (canvas.winfo_width(), canvas.winfo_height()))
        mx, my = origin[0] - self._dz_origin[0], origin[1] - self._dz_origin[1]
        canvas.move("all", mx, my)                      # cheap: no redraw while dragging
        self._dz_origin = origin
        self._dz()["view"] = {"s": p["scale"], "ox": origin[0], "oy": origin[1]}

    def _dz_pan_release(self, _event):
        p, self._dz_pan = self._dz_pan, None
        if p is None:
            return
        self._dz_canvas.configure(cursor="hand2" if self._dz_space else "")
        if p["deselect"] and not p["moved"] and self._dz().get("sel"):
            self._dz()["sel"] = None
            self._dz_update(code=False)

    # ---- structure list (collapsible) --------------------------------------
    def _dz_outline(self, parent, tree, pack):
        st = self._dz()
        frame = tk.Frame(parent, bg=DARK_PANEL)
        frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        shown = st.get("outline_open", True)
        head = tk.Label(frame, text=("▾ Structure" if shown else "▸ Structure"), bg=DARK_PANEL, fg="#888888",
                        font=("Segoe UI", 9, "bold"), anchor="w", cursor="hand2")
        head.pack(fill=tk.X, padx=8, pady=(4, 2))
        head.bind("<Button-1>", lambda e: self._dz_toggle_outline())
        if not shown:
            self._dz_out = None
            return
        out = ttk.Treeview(frame, show="tree", selectmode="browse", style="Designer.Treeview", height=5)
        out.pack(fill=tk.X, padx=4, pady=(0, 4))
        for wid, parent_id, label, _depth in dm.outline_rows(tree):
            out.insert(parent_id, "end", iid=wid, text=label, open=True)
        sel = st.get("sel")
        if sel and out.exists(sel):
            out.selection_set(sel)
            out.see(sel)
        out.bind("<<TreeviewSelect>>", self._dz_on_select)
        self._dz_out = out

    def _dz_toggle_outline(self):
        st = self._dz()
        st["outline_open"] = not st.get("outline_open", True)
        self._dz_rebuild_outline(self._dz_tree_now(), self.port.pack())

    def _dz_on_select(self, _event=None):
        picked = self._dz_out.selection()
        sel = picked[0] if picked else None
        if sel == self._dz().get("sel"):
            return                      # the echo of our own selection_set
        self._dz()["sel"] = sel
        self.host.after_idle(lambda: self._dz_update(code=False))

    # ---- properties panel -------------------------------------------------
    def _dz_render_props(self, tree, pack):
        frame = self._dz_props_frame
        for child in frame.winfo_children():
            child.destroy()
        self._dz_side_header(frame, "Settings", "hide_props")
        sel_id = self._dz().get("sel")
        widget = tree.find(sel_id) if sel_id else None
        if widget is None:
            tk.Label(frame, text="Click a widget on the paper\nto edit its settings.", bg=DARK_PANEL,
                     fg="#777777", font=("Segoe UI", 9), justify=tk.LEFT).pack(padx=10, pady=14, anchor="w")
            return
        wdef = pack.widget(widget["type"])
        if wdef is None:
            tk.Label(frame, text=f"Unknown widget type '{widget['type']}'.\nIt is kept but can't be edited.",
                     bg=DARK_PANEL, fg="#c98f2a", font=("Segoe UI", 9), justify=tk.LEFT).pack(padx=10, pady=14, anchor="w")
            return
        wid = widget["id"]
        self._dz_section(frame, f"{wdef['label']}")
        if wdef.get("description"):
            tk.Label(frame, text=wdef["description"], bg=DARK_PANEL, fg="#8a8a8a", font=("Segoe UI", 9),
                     wraplength=250, justify=tk.LEFT, anchor="w").pack(fill=tk.X, padx=10, pady=(0, 6))
        if wid != tree.root["id"]:
            acts = tk.Frame(frame, bg=DARK_PANEL)
            acts.pack(fill=tk.X, padx=10, pady=(0, 4))
            for text, cmd in (("Duplicate", self._dz_duplicate), ("▲", lambda: self._dz_move(-1)),
                              ("▼", lambda: self._dz_move(1)), ("Remove", self._dz_remove)):
                self._dz_button(acts, text, cmd).pack(side=tk.LEFT, padx=(0, 3))
        self._dz_field(frame, "Variable name", widget["name"], lambda text, w=wid: self._dz_rename(w, text))
        for p in wdef["props"]:
            self._dz_prop_row(frame, tree, wid, widget, p)
        if pack.layouts and widget["id"] != tree.root["id"]:
            self._dz_section(frame, "Layout")
            self._dz_layout_rows(frame, tree, pack, widget)
        if wdef["events"]:
            self._dz_section(frame, "Events")
            names = self._dz_function_names()
            for ev in wdef["events"]:
                self._dz_event_row(frame, wid, widget, ev, names)

    def _dz_section(self, parent, text):
        tk.Label(parent, text=text, bg=DARK_PANEL, fg="#9cdcfe", font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill=tk.X, padx=10, pady=(10, 2))

    def _dz_row(self, parent, label):
        row = tk.Frame(parent, bg=DARK_PANEL)
        row.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(row, text=label, bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9), width=14,
                 anchor="w").pack(side=tk.LEFT)
        return row

    def _dz_field(self, parent, label, value, on_commit):
        """Text box that commits on Enter / leaving the field."""
        row = self._dz_row(parent, label)
        var = tk.StringVar(value=value)
        entry = tk.Entry(row, textvariable=var, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG,
                         relief=tk.FLAT, highlightthickness=1, highlightbackground=DARK_BORDER,
                         highlightcolor=DARK_ACCENT)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        original = [value]

        def commit(_e=None):
            text = var.get()
            if text != original[0]:
                original[0] = text
                on_commit(text)
        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        return entry

    def _dz_combo(self, parent, label, values, current, on_pick):
        row = self._dz_row(parent, label)
        var = tk.StringVar(value=current)
        box = ttk.Combobox(row, textvariable=var, values=values, state="readonly")
        box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        box.bind("<<ComboboxSelected>>", lambda e: on_pick(var.get()))
        return box

    def _dz_prop_row(self, parent, tree, wid, widget, p):
        value = widget["props"].get(p["key"])
        if p["kind"] == "bool":
            row = self._dz_row(parent, p["label"])
            var = tk.BooleanVar(value=bool(value))
            tk.Checkbutton(row, variable=var, bg=DARK_PANEL, activebackground=DARK_PANEL, selectcolor=DARK_BG,
                           command=lambda: self._dz_set_prop(wid, p, var.get())).pack(side=tk.LEFT)
        elif p["kind"] == "enum":
            self._dz_combo(parent, p["label"], p["options"], "" if value is None else str(value),
                           lambda v: self._dz_set_prop(wid, p, v))
        elif p["kind"] == "color":
            self._dz_color_row(parent, wid, p, value)
        elif p["kind"] == "font":
            self._dz_font_row(parent, wid, p, value)
        else:
            def commit(text, p=p):
                ok, parsed = dm.coerce_value(p["kind"], text)
                if not ok:
                    self.host.bell()
                    self.host.after_idle(lambda: self._dz_update(code=False))   # put the old value back
                    return
                self._dz_set_prop(wid, p, parsed)
            self._dz_field(parent, p["label"], dm.show_value(p["kind"], value), commit)

    def _dz_color_row(self, parent, wid, p, value):
        """Colour as text (#rrggbb or a name) plus a swatch that opens a picker.
        Empty = the library's default."""
        row = self._dz_row(parent, p["label"])
        swatch = tk.Label(row, text="  ", width=2, relief=tk.FLAT, cursor="hand2",
                          bg=DARK_BG, highlightthickness=1, highlightbackground=DARK_BORDER)
        try:
            swatch.configure(bg=value or DARK_BG)
        except tk.TclError:
            swatch.configure(bg=DARK_BG)                  # a colour name Tk doesn't know
        swatch.pack(side=tk.RIGHT, padx=(4, 0))
        var = tk.StringVar(value=value or "")
        entry = tk.Entry(row, textvariable=var, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, width=10,
                         relief=tk.FLAT, highlightthickness=1, highlightbackground=DARK_BORDER, highlightcolor=DARK_ACCENT)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def commit(_e=None):
            text = var.get().strip()
            if text != (value or ""):
                self._dz_set_prop(wid, p, text or None)

        def pick(_e=None):
            try:
                _rgb, hexcode = colorchooser.askcolor(color=value or None, parent=self.host.frame, title=p["label"])
            except tk.TclError:
                _rgb, hexcode = colorchooser.askcolor(parent=self.host.frame, title=p["label"])
            if hexcode:
                self._dz_set_prop(wid, p, hexcode)
        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        swatch.bind("<Button-1>", pick)

    def _dz_font_row(self, parent, wid, p, value):
        """Font family, size and bold/italic; all unset = the default font."""
        family, size, styles = ui_paper.parse_font(value)
        row = self._dz_row(parent, p["label"])
        fam_var = tk.StringVar(value=family)
        size_var = tk.StringVar(value=str(size))
        bold_var = tk.BooleanVar(value="bold" in styles)
        italic_var = tk.BooleanVar(value="italic" in styles)

        def commit(_e=None):
            try:
                n = int(size_var.get())
            except ValueError:
                self.host.bell()
                return
            n = max(4, min(n, 200))
            new = ui_paper.format_font(fam_var.get(), n, [s for s, v in (("bold", bold_var), ("italic", italic_var)) if v.get()])
            if new != value:
                self._dz_set_prop(wid, p, new)
        fam = ttk.Combobox(row, textvariable=fam_var, values=FONT_FAMILIES, width=10)
        fam.pack(side=tk.LEFT, fill=tk.X, expand=True)
        fam.bind("<<ComboboxSelected>>", commit)
        fam.bind("<Return>", commit)
        spin = tk.Spinbox(row, from_=4, to=200, textvariable=size_var, width=4, command=commit, bg=DARK_BG, fg=DARK_FG,
                          insertbackground=DARK_FG, buttonbackground="#3a3a3a", relief=tk.FLAT)
        spin.pack(side=tk.LEFT, padx=(4, 0))
        spin.bind("<Return>", commit)
        spin.bind("<FocusOut>", commit)
        row2 = tk.Frame(parent, bg=DARK_PANEL)
        row2.pack(fill=tk.X, padx=(10 + 14 * 7, 10), pady=(0, 2))
        for text, var in (("Bold", bold_var), ("Italic", italic_var)):
            tk.Checkbutton(row2, text=text, variable=var, command=commit, bg=DARK_PANEL, fg=DARK_FG,
                           activebackground=DARK_PANEL, activeforeground=DARK_FG, selectcolor=DARK_BG,
                           font=("Segoe UI", 8)).pack(side=tk.LEFT)
        if value:
            reset = tk.Label(row2, text="reset", bg=DARK_PANEL, fg="#888888", cursor="hand2", font=("Segoe UI", 8, "underline"))
            reset.pack(side=tk.RIGHT)
            reset.bind("<Button-1>", lambda e: self._dz_set_prop(wid, p, None))

    def _dz_layout_rows(self, parent, tree, pack, widget):
        wid = widget["id"]
        managers = [NONE_LABEL] + list(pack.layouts)
        current = widget["layout"].get("manager") or NONE_LABEL
        self._dz_combo(parent, "Placement", managers, current, lambda v: self._dz_set_layout(wid, manager=None if v == NONE_LABEL else v))
        spec = pack.layouts.get(widget["layout"].get("manager"))
        for p in (spec["props"] if spec else []):
            def commit(text, p=p):
                ok, parsed = dm.coerce_value(p["kind"], text)
                if not ok:
                    self.host.bell()
                    self.host.after_idle(lambda: self._dz_update(code=False))
                    return
                self._dz_set_layout(wid, **{p["key"]: parsed})
            self._dz_field(parent, p["label"], dm.show_value(p["kind"], widget["layout"].get(p["key"])), commit)

    def _dz_function_names(self):
        """[(name, id)] of the functions an event can call."""
        return [(OPEN_WINDOW + name if is_window else name, fid)
                for name, fid, is_window in self.port.handler_targets()]

    def _dz_event_row(self, parent, wid, widget, ev, names):
        target = widget["events"].get(ev["key"])
        by_id = {i: n for n, i in names}
        current = by_id.get(target, NONE_LABEL if target is None else f"{target} (missing)")
        choices = [NONE_LABEL, NEW_LABEL] + [n for n, _i in names]

        def pick(label, key=ev["key"]):
            ids = dict(names)
            if label == NEW_LABEL:
                new_id = self._dz_new_handler(widget["name"], key)
                self._dz_apply(lambda t: t.set_event(wid, key, new_id))
                return
            self._dz_apply(lambda t: t.set_event(wid, key, None if label == NONE_LABEL else ids.get(label)))
        box = self._dz_combo(parent, ev["label"], choices, current, pick)
        if target in by_id:                                  # jump to the function that runs
            go = tk.Label(box.master, text="Open", bg=DARK_BG, fg=DARK_FG, cursor="hand2", padx=8, pady=2,
                          font=("Segoe UI", 9), highlightthickness=1, highlightbackground=DARK_BORDER)
            go.pack(side=tk.LEFT, padx=(6, 0))
            go.bind("<Button-1>", lambda e, t=target: (self.port.open_node(t), "break")[1])

    # ---- edits ----------------------------------------------------------
    def _dz_apply(self, change):
        """Run `change(tree)`, save the tree into the node and refresh."""
        tree = self._dz_tree()
        try:
            change(tree)
        except (ValueError, KeyError) as e:
            messagebox.showinfo("UI builder", str(e))
            return
        self.port.store_tree(tree)
        self.port.mark_dirty()
        self.host.after_idle(self._dz_update)

    def _dz_set_prop(self, wid, p, value):
        if value is None:
            self._dz_apply(lambda t: t.clear_prop(wid, p["key"]))
        else:
            self._dz_apply(lambda t: t.set_prop(wid, p["key"], value))

    def _dz_set_layout(self, wid, **values):
        def change(t):
            node = t.find(wid)
            for k, v in values.items():
                if v is None:
                    node["layout"].pop(k, None)
            t.set_layout(wid, **{k: v for k, v in values.items() if v is not None})
        self._dz_apply(change)

    def _dz_rename(self, wid, text):
        self._dz_apply(lambda t: t.rename(wid, text.strip()))

    def _dz_add_type(self, wtype):
        pack = self.port.pack()
        st = self._dz()
        added = []

        def change(t):
            new_id = dm.add_widget(t, pack, wtype, st.get("sel"))
            if new_id is not None:
                added.append(new_id)
        self._dz_apply(change)
        if added:
            st["sel"] = added[0]
            wid = added[0]
            self.host.after_idle(lambda: self._dz_edit_text(wid))     # type the text right away, Esc keeps the default

    def _dz_remove(self):
        sel = self._dz().get("sel")
        if sel:
            self._dz()["sel"] = None
            self._dz_apply(lambda t: t.remove(sel))

    def _dz_duplicate(self):
        sel = self._dz().get("sel")
        if sel:
            made = []
            self._dz_apply(lambda t: made.append(t.duplicate(sel)))
            if made:
                self._dz()["sel"] = made[0]

    def _dz_move(self, delta):
        sel = self._dz().get("sel")
        if sel:
            self._dz_apply(lambda t: dm.move_sibling(t, sel, delta))

    def _dz_undo(self):
        self._dz_history(lambda t: t.undo())

    def _dz_redo(self):
        self._dz_history(lambda t: t.redo())

    def _dz_history(self, step):
        tree = self._dz_tree()
        if step(tree):
            self.port.store_tree(tree)
            self.port.mark_dirty()
            self._dz_update()

    def _dz_detach(self):
        """No confirm: "Back to designer" reads the code back afterwards."""
        self.port.detach()
        self._dz().clear()
        self.port.mark_dirty()
        self.host.refresh()

    def _dz_new_handler(self, widget_name, event_key):
        """Add an empty function node (on_<widget>_<event>) next to the UI node
        and return its id, so an event can point at it straight away."""
        return self.port.create_handler(widget_name, event_key)

    # ---- preview ----------------------------------------------------------
    def _dz_preview(self):
        """Run just this window in its own process. Handlers are stubs that
        print, so nothing else of the project runs."""
        source, problems = self.port.preview_source()
        if source is None:
            messagebox.showinfo("Preview", "\n".join(problems) or "Nothing to preview.")
            return
        old = self.__dict__.get("_dz_preview_proc")
        if old is not None and old.poll() is None:
            old.terminate()
        fd, path = tempfile.mkstemp(suffix=".py", prefix="blockliner_preview_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source)
        try:
            proc = subprocess.Popen([sys.executable, path], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True)
        except OSError as e:
            os.unlink(path)
            messagebox.showerror("Preview", str(e))
            return
        self._dz_preview_proc = proc

        def watch():
            err = proc.stderr.read() if proc.stderr else ""
            code = proc.wait()
            try:
                os.unlink(path)
            except OSError:
                pass
            if code not in (0, None) and err.strip() and code > 0:
                self.host.after(0, lambda: messagebox.showerror("Preview failed", err.strip()[-1500:]))
        threading.Thread(target=watch, daemon=True).start()
