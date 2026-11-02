"""Extensions in the app: the icon strip and "..." menu, side panels, and the
manager window (Tools > Extensions...). The rules are pure (extensions.py,
extensions_builtin.py); this file only shows them. See docs/design-extensions.md.

First slice: the two extensions that ship with Blockliner. Outside extensions are
read and listed, with their compatibility, but not started yet (the process
runner comes next), so the manager marks them "not started yet".
"""
import json
import os
import tkinter as tk

import extensions as X
import extensions_builtin as B
from panels import PanelSpec
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, get_bundle_path

OK_COLOR, WARN_COLOR, BAD_COLOR = "#4caf50", "#e5a50a", "#d9534f"
REFRESH_MS = 1500


class ExtensionsMixin:

    def extension_roots(self):
        return [(os.path.join(get_bundle_path(), "extensions", "builtin"), "built-in"),
                (os.path.join(os.path.dirname(APP_SETTINGS_PATH), "extensions"), "user")]

    def install_extensions(self):
        self._ext_all = X.find_extensions(self.extension_roots())
        self._ext_panels = {}           # panel id -> {"ext", "body", "shown": json text}
        self.refresh_extensions()
        self.after(REFRESH_MS, self._ext_tick)

    def _ext_runnable(self, ext):
        """Only the extensions shipped with Blockliner run in this first slice."""
        return ext["manifest"] is not None and bool(ext["manifest"]["builtin"])

    def refresh_extensions(self):
        active = [e for e in X.active(self._ext_all, self.settings) if self._ext_runnable(e)]
        self._ext_layout = X.layout(active)
        live = {f"ext:{e['manifest']['id']}" for e in active}
        for pid in list(self._ext_panels):
            if pid not in live and pid in self.panels.ids():
                self.panels.hide(pid)
        self.draw_extension_bar()

    # ---- icon strip and "..." menu ---------------------------------------------
    def draw_extension_bar(self):
        bar = self.plugin_bar
        for w in bar.winfo_children():
            w.destroy()
        lay = self._ext_layout

        def flat(text, font):
            return tk.Button(bar, text=text, bg=DARK_PANEL, fg=DARK_FG, activebackground=DARK_HOVER,
                             activeforeground=DARK_FG, relief=tk.FLAT, bd=0, padx=8, pady=4, font=font,
                             cursor="hand2", highlightthickness=0)
        for ext in lay["pinned"]:
            m = ext["manifest"]
            shown = f"ext:{m['id']}" in self.panels.ids() and self.panels.is_visible(f"ext:{m['id']}")
            b = flat(m["icon"], ("Segoe UI Emoji", 12))
            if shown:
                b.configure(bg=DARK_ACCENT)
            b.configure(command=lambda e=ext: self.toggle_extension_panel(e))
            b.pack(side=tk.LEFT)
        more = tk.Menubutton(bar, text="⋯", bg=DARK_PANEL, fg=DARK_FG, activebackground=DARK_HOVER,
                             activeforeground=DARK_FG, relief=tk.FLAT, bd=0, padx=8, pady=4,
                             font=("Segoe UI", 12, "bold"), cursor="hand2", highlightthickness=0)
        menu = self._new_menu(more)
        for ext in lay["overflow_panels"]:
            m = ext["manifest"]
            menu.add_command(label=f"{m['icon']}  {m['panel']['title']}", command=lambda e=ext: self.toggle_extension_panel(e))
        for ext, command in lay["commands"]:
            menu.add_command(label=command["label"], command=lambda e=ext, c=command["command"]: self.extension_command(e, c))
        if menu.index("end") is not None:
            menu.add_separator()
        menu.add_command(label="Manage extensions...", command=self.show_extension_manager)
        more.configure(menu=menu)
        more.pack(side=tk.LEFT)

    # ---- panels -----------------------------------------------------------------
    def toggle_extension_panel(self, ext):
        m = ext["manifest"]
        pid = f"ext:{m['id']}"
        if pid in self.panels.ids():
            if self.panels.is_visible(pid):
                self.panels.hide(pid)
            else:
                self.panels.show(pid)
                self.render_extension_panel(pid)
        else:
            frame = self.panels.create_panel(
                PanelSpec(pid, m["panel"]["title"], dock=m["panel"]["dock"], width=m["panel"]["width"], min_width=160),
                bg=DARK_PANEL)
            head = tk.Frame(frame, bg=DARK_PANEL)
            head.pack(fill=tk.X, padx=10, pady=(10, 4))
            tk.Label(head, text=f"{m['icon']}  {m['panel']['title']}", bg=DARK_PANEL, fg=DARK_FG,
                     font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
            tk.Button(head, text="✕", command=lambda: (self.panels.hide(pid), self.draw_extension_bar()),
                      bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, bd=0, cursor="hand2",
                      activebackground=DARK_HOVER, activeforeground=DARK_FG).pack(side=tk.RIGHT)
            body = tk.Frame(frame, bg=DARK_PANEL)
            body.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
            self._ext_panels[pid] = {"ext": ext, "body": body, "shown": ""}
            self.render_extension_panel(pid)
        self.draw_extension_bar()

    def _panel_description(self, ext):
        build = B.PANELS.get(ext["manifest"]["builtin"])
        return build(self.tabs) if build else None

    def render_extension_panel(self, pid):
        info = self._ext_panels.get(pid)
        if info is None:
            return
        desc = self._panel_description(info["ext"])
        text = json.dumps(desc, sort_keys=True)
        if text == info["shown"]:
            return                                   # nothing changed: no flicker
        info["shown"] = text
        for w in info["body"].winfo_children():
            w.destroy()
        if desc:
            self._draw_description(info["body"], desc, info["ext"])

    def _ext_tick(self):
        for pid, info in list(self._ext_panels.items()):
            try:
                if pid in self.panels.ids() and self.panels.is_visible(pid):
                    self.render_extension_panel(pid)
            except tk.TclError:
                pass
        self.after(REFRESH_MS, self._ext_tick)

    def _draw_description(self, parent, node, ext):
        """Draw a widget description (see extensions_builtin.py). Unknown types are skipped."""
        kind = node.get("type") if isinstance(node, dict) else None
        if kind in ("column", "row"):
            frame = tk.Frame(parent, bg=DARK_PANEL)
            frame.pack(fill=tk.X, pady=2)
            for i, child in enumerate(node.get("children") or []):
                if kind == "row":
                    holder = tk.Frame(frame, bg=DARK_PANEL)
                    holder.pack(side=tk.LEFT if i == 0 else tk.RIGHT)
                    self._draw_description(holder, child, ext)
                else:
                    self._draw_description(frame, child, ext)
        elif kind == "label":
            style = node.get("style")
            tk.Label(parent, text=str(node.get("text", "")), bg=DARK_PANEL, anchor="w", justify=tk.LEFT,
                     fg="#888888" if style == "muted" else DARK_FG,
                     font=("Segoe UI", 10, "bold") if style == "title" else ("Segoe UI", 9)).pack(fill=tk.X)
        elif kind == "button":
            tk.Button(parent, text=str(node.get("text", "")), command=lambda c=node.get("command"): self.extension_command(ext, c),
                      bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2", activebackground=DARK_BORDER,
                      activeforeground=DARK_FG, font=("Segoe UI", 9), padx=8).pack(anchor="w", pady=4)

    # ---- commands -----------------------------------------------------------------
    def extension_command(self, ext, command):
        """A button or menu entry of an extension was used."""
        if command == "refresh":
            for pid, info in self._ext_panels.items():
                if info["ext"] is ext:
                    info["shown"] = ""
                    self.render_extension_panel(pid)
            return
        tab = self.tabs[self.active_tab_index]
        result = B.run_command(ext["manifest"]["builtin"], command, {"code": self.generate_code_for_tab(tab)})
        if result.get("clipboard") is not None:
            self.clipboard_clear()
            self.clipboard_append(result["clipboard"])
        if result.get("notify"):
            self.maybe_notify(ext["manifest"]["name"], result["notify"])

    # ---- manager window --------------------------------------------------------------
    def show_extension_manager(self):
        existing = getattr(self, "_ext_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        win = tk.Toplevel(self)
        self._ext_win = win
        win.title("Extensions")
        win.configure(bg=DARK_PANEL)
        win.geometry("760x520")
        win.minsize(600, 400)
        win.transient(self)

        def label(parent, text, **kw):
            return tk.Label(parent, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w",
                            font=kw.pop("font", ("Segoe UI", 9)), **kw)

        label(win, "Extensions", font=("Segoe UI", 12, "bold")).pack(fill=tk.X, padx=14, pady=(12, 0))
        safe = X.safe_start(self.settings)
        label(win, "Safe start is on: every extension is off until you turn it off in Settings or unset BLOCKLINER_SAFE."
              if safe else "Only install extensions you trust: they run as programs on your computer.",
              fg=WARN_COLOR if safe else "#888888", wraplength=700, justify=tk.LEFT).pack(fill=tk.X, padx=14, pady=(0, 8))
        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))
        left = tk.Frame(body, bg=DARK_BG, width=260)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        right = tk.Frame(body, bg=DARK_PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        def show_detail(ext):
            for w in right.winfo_children():
                w.destroy()
            m = ext["manifest"]
            if m is None:
                label(right, "This extension can't be used", font=("Segoe UI", 10, "bold"), fg=BAD_COLOR).pack(fill=tk.X)
                label(right, os.path.basename(ext["folder"]), fg="#888888").pack(fill=tk.X)
                for note in ext["notes"]:
                    label(right, note, fg=BAD_COLOR, wraplength=420, justify=tk.LEFT).pack(fill=tk.X, pady=2)
                return
            status, reason = X.compatibility(m)
            label(right, f"{m['icon']}  {m['name']}", font=("Segoe UI", 11, "bold")).pack(fill=tk.X)
            label(right, f"{m['id']}   version {m['extension_version']}   by {m['author'] or 'unknown'}", fg="#888888").pack(fill=tk.X)
            label(right, m["description"], wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 6))
            label(right, X.STATUS_TEXT[status] + (f": {reason}" if reason else ""),
                  fg=OK_COLOR if status == "ok" else BAD_COLOR, wraplength=440, justify=tk.LEFT).pack(fill=tk.X)
            if not self._ext_runnable(ext):
                label(right, "Not started yet: outside extensions can be read and listed, but running them comes in the next step.",
                      fg=WARN_COLOR, wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(4, 0))
            label(right, "Permissions", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, pady=(10, 2))
            for p in m["permissions"] or []:
                label(right, f"• {X.PERMISSIONS[p]}", fg="#bbbbbb", wraplength=440, justify=tk.LEFT).pack(fill=tk.X)
            if not m["permissions"]:
                label(right, "None", fg="#888888").pack(fill=tk.X)
            if m["panel"]:
                label(right, f"Panel: {m['panel']['title']} ({m['panel']['dock']}, {'pinned icon' if m['pin'] else 'in the ⋯ menu'})",
                      fg="#bbbbbb").pack(fill=tk.X, pady=(8, 0))
            for c in m["commands"]:
                label(right, f"Command: {c['label']} ({c['menu']})", fg="#bbbbbb").pack(fill=tk.X)
            for note in ext["notes"]:
                label(right, note, fg=WARN_COLOR, wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 0))
            label(right, f"{ext['scope']}  •  {ext['folder']}", fg="#666666", wraplength=440, justify=tk.LEFT).pack(fill=tk.X, pady=(10, 0))

        def toggle(ext, var):
            X.set_enabled(self.settings, ext["manifest"]["id"], var.get())
            self.save_app_settings()
            self.refresh_extensions()

        if not self._ext_all:
            label(left, "No extensions found.", fg="#888888").pack(padx=8, pady=8)
        for ext in self._ext_all:
            row = tk.Frame(left, bg=DARK_BG)
            row.pack(fill=tk.X)
            m = ext["manifest"]
            if m is not None and X.compatibility(m)[0] == "ok":
                var = tk.BooleanVar(value=X.is_enabled(m, self.settings))
                tk.Checkbutton(row, variable=var, command=lambda e=ext, v=var: toggle(e, v), bg=DARK_BG,
                               activebackground=DARK_BG, selectcolor=DARK_PANEL).pack(side=tk.LEFT)
            else:
                tk.Label(row, text=" ⚠ ", bg=DARK_BG, fg=BAD_COLOR).pack(side=tk.LEFT)
            name = tk.Label(row, text=m["name"] if m else os.path.basename(ext["folder"]), bg=DARK_BG,
                            fg=DARK_FG if m and X.compatibility(m)[0] == "ok" else "#777777", anchor="w",
                            cursor="hand2", font=("Segoe UI", 9))
            name.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=4)
            name.bind("<Button-1>", lambda _e, x=ext: show_detail(x))
        if self._ext_all:
            show_detail(self._ext_all[0])
        win.bind("<Escape>", lambda _e: win.destroy())
        return win
