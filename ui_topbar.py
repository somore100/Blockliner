"""Top bar menus (hamburger + File/Run/Tools/Help) and the About window."""
import tkinter as tk
import webbrowser
from PIL import Image, ImageTk

import about_info
from ui_common import DARK_ACCENT, DARK_BG, DARK_FG, DARK_HOVER, DARK_PANEL, get_bundle_path


class TopBarMixin:
    def topbar_menu_spec(self):
        """[(title, [(label, command) | None for a separator])]"""
        return [
            ("File", [
                ("Save", self.save_project),
                ("Load", self.load_project),
                ("Open Code File...", lambda: self.open_code_to_blocks_dialog(prefill_from_file=True)),
                ("Export", self.export_code),
            ]),
            ("Run", [
                ("Run in Blockliner", self.run_code),
                ("Run in Terminal", self.run_in_terminal),
                ("Open in VS Code", self.open_in_vscode),
                None,
                ("Export & Run...", self.export_and_run),
                None,
                ("Clear", self.clear_all),
            ]),
            ("Tools", [
                ("Manage Custom Blocks...", self.manage_custom_blocks_dialog),
                ("Settings", self.settings_dialog),
            ]),
            ("Help", [
                ("About Blockliner", self.show_about),
            ]),
        ]

    def _fill_menu(self, menu, entries):
        for e in entries:
            if e is None:
                menu.add_separator()
            else:
                menu.add_command(label=e[0], command=e[1])

    def build_topbar(self, toolbar):
        """Menus on the left of the toolbar, plugin-icon strip on the right."""
        spec = self.topbar_menu_spec()
        bar = tk.Frame(toolbar, bg=DARK_PANEL)
        bar.pack(side=tk.LEFT, padx=(4, 0))
        self.topbar_menus = {}

        def flat(parent, text, font):
            b = tk.Menubutton(parent, text=text, bg=DARK_PANEL, fg=DARK_FG,
                              activebackground=DARK_HOVER, activeforeground=DARK_FG,
                              relief=tk.FLAT, bd=0, padx=10, pady=6, font=font,
                              cursor="hand2", highlightthickness=0)
            return b

        # Hamburger: everything, as cascades.
        burger = flat(bar, "☰", ("Segoe UI", 13))
        hmenu = self._new_menu(burger)
        for title, entries in spec:
            sub = self._new_menu(hmenu)
            self._fill_menu(sub, entries)
            hmenu.add_cascade(label=title, menu=sub)
        burger.configure(menu=hmenu)
        burger.pack(side=tk.LEFT)
        self.topbar_menus["☰"] = hmenu

        # Menu bar: one flat dropdown per section.
        for title, entries in spec:
            b = flat(bar, title, ("Segoe UI", 10))
            m = self._new_menu(b)
            self._fill_menu(m, entries)
            b.configure(menu=m)
            b.pack(side=tk.LEFT)
            self.topbar_menus[title] = m

        # Reserved, empty on purpose: icons from future addons/plugins.
        self.plugin_bar = tk.Frame(toolbar, bg=DARK_PANEL)
        self.plugin_bar.pack(side=tk.RIGHT, padx=8)

    # ---------------------------------------------------------- About
    def show_about(self, tab="About"):
        win = getattr(self, "_about_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            self._about_show_tab(tab)
            return win
        win = tk.Toplevel(self)
        self._about_win = win
        win.title("About Blockliner")
        win.configure(bg=DARK_BG)
        win.geometry("460x440")
        win.minsize(380, 360)
        win.transient(self)
        win.bind("<Escape>", lambda e: win.destroy())
        try:
            win.geometry("+%d+%d" % (self.winfo_rootx() + 120, self.winfo_rooty() + 80))
        except tk.TclError:
            pass

        # Logo + name + version
        head = tk.Frame(win, bg=DARK_BG)
        head.pack(fill=tk.X, pady=(18, 6))
        try:
            img = Image.open(self._about_logo_path()).resize((88, 88), Image.Resampling.LANCZOS)
            win._logo = ImageTk.PhotoImage(img)
            tk.Label(head, image=win._logo, bg=DARK_BG).pack()
        except Exception:
            tk.Label(head, text="⬢", bg=DARK_BG, fg=DARK_ACCENT, font=("Segoe UI", 40)).pack()
        tk.Label(head, text=about_info.APP_NAME, bg=DARK_BG, fg=DARK_ACCENT,
                 font=("Segoe UI", 18, "bold")).pack()
        tk.Label(head, text=about_info.TAGLINE, bg=DARK_BG, fg="#aaaaaa",
                 font=("Segoe UI", 9)).pack()
        tk.Label(head, text=about_info.version_text(), bg=DARK_BG, fg="#888888",
                 font=("Segoe UI", 9)).pack(pady=(2, 0))

        # Tab buttons
        tabs = tk.Frame(win, bg=DARK_PANEL)
        tabs.pack(fill=tk.X, padx=14)
        win._tab_buttons = {}
        for name in ("About", "Credits", "License"):
            b = tk.Button(tabs, text=name, relief=tk.FLAT, bd=0, padx=14, pady=4,
                          cursor="hand2", font=("Segoe UI", 9),
                          command=lambda n=name: self._about_show_tab(n))
            b.pack(side=tk.LEFT)
            win._tab_buttons[name] = b

        # Body
        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))
        sb = tk.Scrollbar(body)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        win._text = tk.Text(body, wrap=tk.WORD, bg=DARK_PANEL, fg=DARK_FG, bd=0,
                            highlightthickness=0, padx=12, pady=10,
                            font=("Segoe UI", 10), yscrollcommand=sb.set)
        win._text.pack(fill=tk.BOTH, expand=True)
        sb.config(command=win._text.yview)

        foot = tk.Frame(win, bg=DARK_BG)
        foot.pack(fill=tk.X, pady=(0, 10))
        link = tk.Label(foot, text=about_info.REPO_URL, bg=DARK_BG, fg=DARK_ACCENT,
                        cursor="hand2", font=("Segoe UI", 9, "underline"))
        link.pack(side=tk.LEFT, padx=16)
        link.bind("<Button-1>", lambda e: webbrowser.open(about_info.REPO_URL))
        tk.Button(foot, text="Close", relief=tk.FLAT, bd=0, padx=16, pady=3,
                  bg=DARK_HOVER, fg=DARK_FG, activebackground=DARK_ACCENT,
                  activeforeground=DARK_FG, cursor="hand2",
                  command=win.destroy).pack(side=tk.RIGHT, padx=16)

        self._about_show_tab(tab)
        win.focus_set()
        return win

    def _about_logo_path(self):
        import os
        return os.path.join(get_bundle_path(), "logo.png")

    def about_tab_text(self, tab):
        if tab == "Credits":
            return about_info.CREDITS
        if tab == "License":
            return about_info.read_license(get_bundle_path())
        return about_info.DESCRIPTION + "\n\nBy " + about_info.AUTHOR

    def _about_show_tab(self, tab):
        win = self._about_win
        for name, b in win._tab_buttons.items():
            on = (name == tab)
            b.configure(bg=DARK_HOVER if on else DARK_PANEL, fg=DARK_FG if on else "#888888",
                        activebackground=DARK_HOVER, activeforeground=DARK_FG)
        t = win._text
        t.configure(state=tk.NORMAL)
        t.delete("1.0", tk.END)
        t.insert("1.0", self.about_tab_text(tab))
        t.configure(state=tk.DISABLED)
        win._current_tab = tab
