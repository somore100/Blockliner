"""Block palette, categories, languages and the settings dialog."""
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import os
import shutil
from block_templates import make_raw_code_block_source
from scroll_modes import SCROLL_MODE_CHOICES, normalize_mode
from code_sync import SYNC_MODE_CHOICES, normalize_sync_mode
from ui_common import CATEGORY_COLORS, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, KEYBIND_ACTIONS, ORDER_CONFLICT_CHOICES, SAVE_FORMAT_CHOICES, get_block_attr, normalize_save_format, keybind_from_event, keybind_label, safe_grab_set
from ui_widgets import PaletteBlockItem


class PaletteMixin:
    
    def get_available_languages(self):
        """Get list of available languages"""
        if not os.path.exists(self.languages_path):
            return ["python"]
        return sorted([d for d in os.listdir(self.languages_path) 
                      if os.path.isdir(os.path.join(self.languages_path, d))])

    def refresh_language_list(self):
        """
        Re-scan languages/ from disk and update the dropdown. The main
        language list is normally only set once at startup (and patched
        by + Lang / delete Lang), so a folder added or removed by hand
        outside the app - e.g. in a file manager or terminal - won't
        show up or disappear on its own until this runs (or the app
        restarts, which does the same scan).
        """
        available = self.get_available_languages()
        self.lang_combo['values'] = available

        if self.current_language not in available:
            fallback = available[0] if available else "python"
            messagebox.showwarning(
                "Language Missing",
                f"'{self.current_language}' no longer has a folder on disk.\n\n"
                f"Switching to '{fallback}'."
            )
            self.lang_var.set(fallback)
            self.on_language_change()

        self.maybe_notify(
            "Languages Refreshed",
            f"Found {len(available)} language(s):\n{', '.join(available)}"
        )
    
    def open_block_chooser_dialog(self, container_list):
        """
        Small popup palette for adding a block into a container block's
        body (e.g. inside an If block). Reuses the same categorized
        block list as the main palette, but clicking an entry adds it
        into container_list instead of the top-level workspace.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Add Block to Body")
        dialog.geometry("360x520")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        header = tk.Frame(dialog, bg="#4a9eff", height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="Add Block to Body", bg="#4a9eff", fg="white",
            font=("Segoe UI", 12, "bold")
        ).pack(side=tk.LEFT, padx=15, pady=10)

        canvas = tk.Canvas(dialog, bg=DARK_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        list_frame = tk.Frame(canvas, bg=DARK_PANEL)
        list_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def choose(block_module):
            dialog.destroy()
            self.add_block_to_workspace(block_module, container_list=container_list)

        for category in self.get_ordered_categories():
            blocks_in_category = self.blocks_by_category.get(category, [])
            if not blocks_in_category:
                continue
            color = CATEGORY_COLORS.get(category, "#ffffff")
            tk.Label(
                list_frame, text=category.upper(), bg=DARK_PANEL, fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(anchor="w", padx=10, pady=(10, 2))
            for block_module in sorted(blocks_in_category, key=lambda x: get_block_attr(x, "display_name", "")):
                name = get_block_attr(block_module, "display_name", "Unknown")
                tk.Button(
                    list_frame, text=f"+ {name}", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
                    anchor="w", cursor="hand2",
                    command=lambda bm=block_module: choose(bm)
                ).pack(fill=tk.X, padx=10, pady=1)

        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def get_ordered_categories(self):
        """
        All currently-populated categories in their persisted display
        order. Any category that exists in the palette but isn't in the
        saved order yet (a brand-new one, or the very first run) gets
        appended alphabetically and the order is persisted, so nothing
        is ever silently missing from the palette.
        """
        present = set(self.blocks_by_category.keys())
        ordered = [c for c in self.category_order if c in present]
        missing = sorted(present - set(ordered))
        if missing:
            ordered.extend(missing)
            self.category_order = ordered
            self.settings["category_order"] = self.category_order
            self.save_app_settings()
        return ordered

    def category_options_menu(self, category, event):
        """Small popup menu from a category's gear icon: recolor or reorder it."""
        menu = tk.Menu(self, tearoff=0, bg=DARK_PANEL, fg=DARK_FG,
                        activebackground=DARK_HOVER, activeforeground=DARK_FG)
        menu.add_command(label=f"\U0001F3A8 Change '{category}' Color",
                          command=lambda: self.change_category_color(category))
        menu.add_separator()
        menu.add_command(label="\u25B2 Move Up", command=lambda: self.reorder_category(category, -1))
        menu.add_command(label="\u25BC Move Down", command=lambda: self.reorder_category(category, 1))
        menu.tk_popup(event.x_root, event.y_root)

    def change_category_color(self, category):
        """Open a native color picker and persist the chosen color for this category."""
        current = CATEGORY_COLORS.get(category, "#ffffff")
        chosen = colorchooser.askcolor(color=current, title=f"Color for '{category}'")
        if chosen and chosen[1]:
            CATEGORY_COLORS[category] = chosen[1]
            self.settings.setdefault("category_colors", {})[category] = chosen[1]
            self.save_app_settings()
            self.refresh_palette()

    def reorder_category(self, category, delta):
        """Move a category up/down in the palette's display order."""
        ordered = self.get_ordered_categories()
        if category not in ordered:
            return
        idx = ordered.index(category)
        new_idx = idx + delta
        if 0 <= new_idx < len(ordered):
            ordered[idx], ordered[new_idx] = ordered[new_idx], ordered[idx]
            self.category_order = ordered
            self.settings["category_order"] = ordered
            self.save_app_settings()
            self.refresh_palette()

    def build_palette(self):
        """Build the block palette"""
        for widget in self.palette_frame.winfo_children():
            widget.destroy()
        
        search_term = self.search_var.get().lower()
        
        if not self.blocks_by_category:
            tk.Label(
                self.palette_frame,
                text=f"No blocks for '{self.current_language}'\n\nAdd blocks to:\nlanguages/{self.current_language}/blocks/",
                bg=DARK_PANEL,
                fg="#888888",
                font=("Segoe UI", 9),
                justify=tk.CENTER
            ).pack(pady=50)
            return

        # "Switch Animation" setting: each header/item still gets built
        # fully immediately (all the actual widget construction below is
        # unchanged) - only the .pack() call that makes each one visible
        # gets deferred a little further than the last, so they cascade
        # in instead of all appearing in the same frame. Off by default
        # so browsing/searching stays instant; this is purely a look.
        animate = self.settings.get("animate_blocks", False)
        stagger_ms = 35
        self._palette_delay_index = 0

        def place(widget, **pack_kwargs):
            if not animate:
                widget.pack(**pack_kwargs)
                return
            delay = self._palette_delay_index * stagger_ms
            self._palette_delay_index += 1

            def do_pack():
                try:
                    if widget.winfo_exists():
                        widget.pack(**pack_kwargs)
                except tk.TclError:
                    pass  # palette was torn down before this fired - fine to ignore

            self.after(delay, do_pack)
        
        for category in self.get_ordered_categories():
            if category not in self.blocks_by_category:
                continue
            blocks_in_category = [
                b for b in self.blocks_by_category[category]
                if not search_term or search_term in get_block_attr(b, "display_name", "").lower() or
                   search_term in get_block_attr(b, "block_ui_description", {}).get("description", "").lower()
            ]
            
            if not blocks_in_category:
                continue
            
            # Category header
            category_header = tk.Frame(self.palette_frame, bg=DARK_PANEL)
            
            color = CATEGORY_COLORS.get(category, "#ffffff")
            
            tk.Label(
                category_header,
                text="▼",
                bg=DARK_PANEL,
                fg=color,
                font=("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=5)
            
            tk.Label(
                category_header,
                text=category.upper(),
                bg=DARK_PANEL,
                fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(side=tk.LEFT)
            
            tk.Label(
                category_header,
                text=f"({len(blocks_in_category)})",
                bg=DARK_PANEL,
                fg="#666666",
                font=("Segoe UI", 8)
            ).pack(side=tk.LEFT, padx=3)

            gear_label = tk.Label(
                category_header,
                text="\u2699",
                bg=DARK_PANEL,
                fg="#888888",
                font=("Segoe UI", 9),
                cursor="hand2"
            )
            gear_label.pack(side=tk.LEFT, padx=6)
            gear_label.bind(
                "<Button-1>",
                lambda e, cat=category: self.category_options_menu(cat, e)
            )

            place(category_header, fill=tk.X, pady=(10, 2))
            
            # Category blocks
            for block_module in sorted(blocks_in_category, key=lambda x: get_block_attr(x, "display_name", "")):
                item = PaletteBlockItem(self.palette_frame, block_module, self.add_block_to_workspace,
                                        self.can_drop_block_at, self.add_block_from_drop,
                                        self.show_drop_indicator)
                place(item, fill=tk.X, pady=1)
    
    def refresh_palette(self):
        """Refresh the palette when language or search changes"""
        self.build_palette()
    
    def filter_palette(self, *args):
        """Filter palette based on search"""
        self.refresh_palette()
    
    def on_language_change(self, event=None):
        """Handle language change"""
        self.current_language = self.lang_var.get()
        if getattr(self, "tabs", None):
            self.tabs[self.active_tab_index]["language"] = self.current_language
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()  # Re-merge custom blocks
        self.refresh_palette()
        self.project_blocks.clear()
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()
    
    def add_language_dialog(self):
        """Prompt user to add a new language folder"""
        def create_language():
            new_lang = entry.get().strip().lower()
            if not new_lang:
                messagebox.showwarning("Invalid", "Language name cannot be empty.")
                return
            new_path = os.path.join(self.languages_path, new_lang)
            if os.path.exists(new_path):
                messagebox.showwarning("Exists", f"Language '{new_lang}' already exists.")
                return
            blocks_path = os.path.join(new_path, "blocks")
            os.makedirs(blocks_path)

            # Every language gets a Raw Code escape-hatch block by default,
            # so there's always a way to write code the block set doesn't
            # cover yet, even before any other blocks exist for it.
            raw_code_path = os.path.join(blocks_path, "raw_code.py")
            with open(raw_code_path, "w") as f:
                f.write(make_raw_code_block_source(new_lang))

            self.maybe_notify("Created", f"Language '{new_lang}' created with a starter Custom Code block.")
            dialog.destroy()
            
            # Refresh language list and select new language
            langs = list(self.lang_combo['values'])
            langs.append(new_lang)
            langs.sort()
            self.lang_combo['values'] = langs
            self.lang_var.set(new_lang)
            self.on_language_change()
        
        dialog = tk.Toplevel(self)
        dialog.title("Add New Language")
        dialog.geometry("300x120")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)
        
        tk.Label(
            dialog,
            text="Enter language name:",
            bg=DARK_PANEL,
            fg=DARK_FG,
            font=("Segoe UI", 10)
        ).pack(pady=10)
        
        entry = tk.Entry(dialog, bg=DARK_BG, fg=DARK_FG, font=("Segoe UI", 10))
        entry.pack(pady=5, padx=10)
        entry.focus()
        
        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Create", command=create_language).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        dialog.bind("<Return>", lambda e: create_language())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def delete_language_dialog(self):
        """Delete the currently selected language's entire folder, after confirming."""
        lang = self.lang_var.get()
        langs = list(self.lang_combo['values'])

        if len(langs) <= 1:
            messagebox.showwarning("Can't Delete", "You need at least one language to remain.")
            return

        lang_path = os.path.join(self.languages_path, lang)
        confirm = messagebox.askyesno(
            "Delete Language",
            f"Delete language '{lang}'?\n\n"
            f"This permanently removes the folder:\n{lang_path}\n\n"
            f"All blocks (including custom ones) defined only for '{lang}' will be lost.\n"
            f"This cannot be undone."
        )
        if not confirm:
            return

        try:
            shutil.rmtree(lang_path)
        except Exception as e:
            messagebox.showerror("Delete Failed", f"Could not delete '{lang}':\n{e}")
            return

        # Also drop any saved custom blocks tagged for this language, so
        # they don't linger in custom_blocks.json pointing at a language
        # that no longer exists.
        self.custom_blocks = [
            cb for cb in self.load_custom_blocks_data()
            if cb.get("language", "all") != lang
        ]
        self.save_custom_blocks_data(self.custom_blocks)

        langs.remove(lang)
        self.lang_combo['values'] = langs
        self.lang_var.set(langs[0])
        self.on_language_change()
        self.maybe_notify("Deleted", f"Language '{lang}' deleted.")

    def settings_dialog(self):
        """App settings: default language, run/compile commands, and
        delete-confirmation preference. Nothing here applies until you
        hit Save & Close - Cancel discards changes."""
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.geometry("560x860")
        dialog.configure(bg=DARK_PANEL)
        dialog.transient(self)
        safe_grab_set(dialog)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        header = tk.Frame(dialog, bg="#569cd6", height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="\u2699 Settings", bg="#569cd6", fg="#000000",
            font=("Segoe UI", 13, "bold")
        ).pack(side=tk.LEFT, padx=20, pady=15)

        # Scrollable body: the rows can outgrow a small screen, and Save & Close
        # must stay reachable, so only this part scrolls.
        scroll_holder = tk.Frame(dialog, bg=DARK_PANEL)
        body_canvas = tk.Canvas(scroll_holder, bg=DARK_PANEL, highlightthickness=0)
        body_scroll = ttk.Scrollbar(scroll_holder, orient="vertical", command=body_canvas.yview)
        body = tk.Frame(body_canvas, bg=DARK_PANEL)
        body_canvas.create_window((0, 0), window=body, anchor="nw", tags="body")
        body.bind("<Configure>", lambda e: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_canvas.bind("<Configure>", lambda e: body_canvas.itemconfigure("body", width=e.width))
        scrollbar_shown = [False]

        def body_yscroll(first, last):
            body_scroll.set(first, last)
            needed = float(first) > 0 or float(last) < 1
            if needed != scrollbar_shown[0]:
                scrollbar_shown[0] = needed
                if needed:
                    body_scroll.pack(side=tk.RIGHT, fill=tk.Y)
                else:
                    body_scroll.pack_forget()
        body_canvas.configure(yscrollcommand=body_yscroll)

        def body_wheel(e):
            if e.num == 4 or (e.num != 5 and getattr(e, "delta", 0) > 0):
                body_canvas.yview_scroll(-1, "units")
            else:
                body_canvas.yview_scroll(1, "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            dialog.bind(seq, body_wheel)

        def add_row(label_text, help_text=None):
            row = tk.Frame(body, bg=DARK_PANEL)
            row.pack(fill=tk.X, pady=(0, 4))
            tk.Label(
                row, text=label_text, bg=DARK_PANEL, fg=DARK_FG,
                font=("Segoe UI", 9, "bold"), width=20, anchor="w"
            ).pack(side=tk.LEFT)
            return row

        def add_help(text):
            tk.Label(
                body, text=text, bg=DARK_PANEL, fg="#888888",
                font=("Segoe UI", 8, "italic"), anchor="w", justify=tk.LEFT, wraplength=460
            ).pack(fill=tk.X, pady=(0, 12))

        # --- Default language ---
        row = add_row("Default language:")
        lang_var = tk.StringVar(value=self.settings.get("default_language", "python"))
        lang_combo = ttk.Combobox(
            row, textvariable=lang_var, values=self.get_available_languages(),
            state="readonly", width=20
        )
        lang_combo.pack(side=tk.LEFT)
        add_help("Which language loads automatically the next time Blockliner starts.")

        # --- Python command ---
        row = add_row("Python command:")
        python_cmd_var = tk.StringVar(value=self.settings.get("python_command", "python3"))
        tk.Entry(
            row, textvariable=python_cmd_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help("Command used to run generated Python code (e.g. 'python3' or 'python').")

        # --- C++ compiler ---
        row = add_row("C++ compiler:")
        cpp_var = tk.StringVar(value=self.settings.get("cpp_compiler", "g++"))
        tk.Entry(
            row, textvariable=cpp_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help("Command used to compile generated C++ code.")

        # --- Terminal command ---
        row = add_row("Terminal command:")
        terminal_var = tk.StringVar(value=self.settings.get("terminal_command", "gnome-terminal --"))
        tk.Entry(
            row, textvariable=terminal_var, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=DARK_BORDER, width=22
        ).pack(side=tk.LEFT, ipady=3)
        add_help(
            "How 'Run in Terminal' opens a terminal window. Linux desktops vary - try "
            "'gnome-terminal --', 'xterm -e', or 'mate-terminal --' depending on what's installed."
        )

        # --- Confirm before delete ---
        confirm_var = tk.BooleanVar(value=self.settings.get("confirm_delete", True))
        tk.Checkbutton(
            body, text="Ask for confirmation before deleting blocks",
            variable=confirm_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Success notification popups ---
        notify_var = tk.BooleanVar(value=self.settings.get("show_notifications", True))
        tk.Checkbutton(
            body, text="Show confirmation popups (e.g. \"Block deleted successfully\")",
            variable=notify_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Switch animation ---
        animate_var = tk.BooleanVar(value=self.settings.get("animate_blocks", False))
        tk.Checkbutton(
            body, text="Animate the block palette loading in (cascades in instead of appearing instantly)",
            variable=animate_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        coords_var = tk.BooleanVar(value=bool(self.settings.get("show_coords", False)))
        tk.Checkbutton(
            body, text="Show x/y numbers on the canvas grid (Files and Nodes layers)",
            variable=coords_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Order number already used ---
        row = add_row("Order number taken:")
        conflict_labels = dict((k, v) for k, v in ORDER_CONFLICT_CHOICES)
        conflict_var = tk.StringVar(value=conflict_labels.get(
            self.settings.get("order_conflict", "take"), conflict_labels["take"]))
        ttk.Combobox(
            row, textvariable=conflict_var, values=[v for _k, v in ORDER_CONFLICT_CHOICES],
            state="readonly", width=38
        ).pack(side=tk.LEFT)
        add_help("What happens when you give a node a number another node already has.")

        # --- Scroll mode ---
        row = add_row("Scroll mode:")
        scroll_labels = dict(SCROLL_MODE_CHOICES)
        scroll_var = tk.StringVar(value=scroll_labels[normalize_mode(self.settings.get("scroll_mode", "smooth"))])
        ttk.Combobox(
            row, textvariable=scroll_var, values=[v for _k, v in SCROLL_MODE_CHOICES],
            state="readonly", width=38
        ).pack(side=tk.LEFT)
        add_help("Smooth scrolls continuously; Rigid snaps to the next block/node with each wheel step.")

        # --- Where node data is saved ---
        row = add_row("Node data saved in:")
        save_labels = dict(SAVE_FORMAT_CHOICES)
        save_var = tk.StringVar(value=save_labels[normalize_save_format(self.settings.get("save_format"))])
        ttk.Combobox(
            row, textvariable=save_var, values=[v for _k, v in SAVE_FORMAT_CHOICES],
            state="readonly", width=38
        ).pack(side=tk.LEFT)
        add_help("Exported code always has node start/end markers. Node names, order and layout go in a separate .blockliner.json file, or inside the code file.")

        # --- Code panel -> blocks sync ---
        row = add_row("Code \u2192 blocks sync:")
        sync_labels = dict(SYNC_MODE_CHOICES)
        sync_var = tk.StringVar(value=sync_labels[normalize_sync_mode(self.settings.get("code_sync_mode"))])
        ttk.Combobox(
            row, textvariable=sync_var, values=[v for _k, v in SYNC_MODE_CHOICES],
            state="readonly", width=38
        ).pack(side=tk.LEFT)
        add_help("When edits typed in the code panel (right side) become blocks.")
        confirm_var = tk.BooleanVar(value=bool(self.settings.get("code_sync_confirm", True)))
        tk.Checkbutton(
            body, text="Ask before code edits replace or remove blocks",
            variable=confirm_var, bg=DARK_PANEL, fg=DARK_FG, selectcolor=DARK_BG,
            activebackground=DARK_PANEL, activeforeground=DARK_FG,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))

        # --- Layer shortcuts ---
        tk.Label(
            body, text="Layer shortcuts", bg=DARK_PANEL, fg=DARK_FG,
            font=("Segoe UI", 9, "bold"), anchor="w"
        ).pack(fill=tk.X, pady=(14, 2))
        key_vars = {}
        key_buttons = {}
        current_binds = self.get_keybinds()

        def start_capture(action):
            btn = key_buttons[action]
            btn.config(text="Press keys\u2026 (Esc cancels)")
            btn.focus_set()

            def on_key(ev):
                if ev.keysym == "Escape":
                    btn.config(text=keybind_label(key_vars[action].get()))
                else:
                    seq = keybind_from_event(ev)
                    if seq is None:
                        return "break"  # modifier alone / plain letter: keep waiting
                    clash = [a for a, v in key_vars.items() if a != action and v.get() == seq]
                    if clash:
                        messagebox.showwarning("Shortcuts", "That shortcut is already used by another action.", parent=dialog)
                        btn.config(text=keybind_label(key_vars[action].get()))
                    else:
                        # Saves the moment the keys are set, like a game's keybind screen.
                        key_vars[action].set(seq)
                        btn.config(text=keybind_label(seq))
                        self.settings["keybinds"] = {a: v.get() for a, v in key_vars.items()}
                        self.apply_keybinds()
                        self.save_app_settings()
                btn.unbind("<KeyPress>")
                return "break"

            btn.bind("<KeyPress>", on_key)

        for action, label in KEYBIND_ACTIONS:
            row = add_row(label + ":")
            key_vars[action] = tk.StringVar(value=current_binds[action])
            btn = tk.Button(
                row, text=keybind_label(key_vars[action].get()), width=22,
                bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                highlightthickness=1, highlightbackground=DARK_BORDER,
                command=lambda a=action: start_capture(a))
            btn.pack(side=tk.LEFT, ipady=2)
            key_buttons[action] = btn
        add_help("Click a shortcut, then press the new keys (a combo like Ctrl+Alt+K works too). It saves right away. Plain letters aren't allowed; arrows and F-keys are, and they pause while you type in a text box.")

        # --- Save / Cancel ---
        btn_frame = tk.Frame(dialog, bg=DARK_PANEL)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 20))
        # Body is packed after the buttons so Save & Close can never be
        # squeezed out when the content grows or the screen is small.
        body.update_idletasks()
        body_canvas.configure(height=body.winfo_reqheight(), width=body.winfo_reqwidth())
        body_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_holder.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        dialog.update_idletasks()
        wanted = (header.winfo_reqheight() + body_canvas.winfo_reqheight()
                  + btn_frame.winfo_reqheight() + 30 + 20 + 10)   # paddings of the three parts
        h = min(wanted, dialog.winfo_screenheight() - 80)
        dialog.geometry(f"560x{h}+{(dialog.winfo_screenwidth() - 560) // 2}+{max(0, (dialog.winfo_screenheight() - h) // 2 - 20)}")

        def on_save_close():
            chosen = [v.get() for v in key_vars.values() if v.get()]
            if len(chosen) != len(set(chosen)):
                messagebox.showwarning("Shortcuts", "Two layers can't share the same shortcut.")
                return
            self.settings["keybinds"] = {a: v.get() for a, v in key_vars.items()}
            self.apply_keybinds()
            self.settings["default_language"] = lang_var.get()
            self.settings["python_command"] = python_cmd_var.get().strip() or "python3"
            self.settings["cpp_compiler"] = cpp_var.get().strip() or "g++"
            self.settings["terminal_command"] = terminal_var.get().strip() or "gnome-terminal --"
            self.settings["confirm_delete"] = confirm_var.get()
            self.settings["show_notifications"] = notify_var.get()
            self.settings["animate_blocks"] = animate_var.get()
            self.settings["show_coords"] = bool(coords_var.get())
            self.settings["order_conflict"] = next(
                (k for k, v in ORDER_CONFLICT_CHOICES if v == conflict_var.get()), "take")
            self.settings["scroll_mode"] = next(
                (k for k, v in SCROLL_MODE_CHOICES if v == scroll_var.get()), "smooth")
            self.settings["save_format"] = next(
                (k for k, v in SAVE_FORMAT_CHOICES if v == save_var.get()), "sidecar")
            self.settings["code_sync_mode"] = next(
                (k for k, v in SYNC_MODE_CHOICES if v == sync_var.get()), "line")
            self.settings["code_sync_confirm"] = bool(confirm_var.get())
            self.save_app_settings()
            dialog.destroy()
            self.redraw_grid()

        def on_cancel():
            dialog.destroy()

        tk.Button(
            btn_frame, text="\U0001F4BE Save & Close", bg="#4ec9b0", fg="#000000",
            font=("Segoe UI", 10, "bold"), relief=tk.FLAT, cursor="hand2",
            command=on_save_close, padx=15, pady=6
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            btn_frame, text="Cancel", bg="#888888", fg="white",
            font=("Segoe UI", 10), relief=tk.FLAT, cursor="hand2",
            command=on_cancel, padx=15, pady=6
        ).pack(side=tk.LEFT, padx=5)

        dialog.bind("<Escape>", lambda e: on_cancel())
