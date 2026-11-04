"""Libraries in the app: command results in the palette search, and per-file
imports. The data and rules are pure (libraries.py); this file only shows them.

A tab (file) keeps `tab["imports"]`, a list of library names. The generated code
starts with their import lines. Searching the palette for a command (say
"sleep") lists matching library commands below the normal blocks:

    green stripe   the library is already imported in this file
    grey stripe    available: clicking asks, then adds its import line
    red stripe     Python only: the module isn't installed on this computer
"""
import os
import tkinter as tk
from tkinter import messagebox

import libraries
from ui_common import DARK_FG, DARK_PANEL, get_block_attr

STATUS_COLORS = {"imported": "#4caf50", "available": "#808080", "not_installed": "#d9534f"}
STATUS_NOTES = {"imported": "already imported", "available": "adds the import", "not_installed": "not installed here"}
MAX_RESULTS = 8


class LibraryResultItem(tk.Frame):
    """One command found in a library; click to add it."""

    def __init__(self, parent, lib, command, status, on_add):
        super().__init__(parent, bg=DARK_PANEL, cursor="hand2")
        color = STATUS_COLORS[status]
        tk.Frame(self, bg=color, width=4).pack(side=tk.LEFT, fill=tk.Y)
        info = tk.Frame(self, bg=DARK_PANEL)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=6)
        tk.Label(info, text=command["name"], bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(info, text=command["signature"], bg=DARK_PANEL, fg="#9cdcfe", font=("Consolas", 8), anchor="w").pack(fill=tk.X)
        if command["does"]:
            tk.Label(info, text=command["does"], bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 8), anchor="w",
                     wraplength=190, justify=tk.LEFT).pack(fill=tk.X)
        tk.Label(info, text=f'{lib["import"]}  ({STATUS_NOTES[status]})', bg=DARK_PANEL, fg=color,
                 font=("Consolas", 8), anchor="w").pack(fill=tk.X, pady=(2, 0))
        for w in (self, info, *info.winfo_children()):
            w.bind("<Button-1>", lambda _e: on_add(lib, command), add="+")


class LibrariesMixin:

    def libraries_for(self, lang):
        """{name: library} of a language pack (cached)."""
        cache = self.__dict__.setdefault("_library_cache", {})
        if lang not in cache:
            cache[lang], _notes = libraries.load_libraries(os.path.join(self.languages_path, lang, "libraries"))
        return cache[lang]

    def tab_imports(self, tab):
        return [n for n in tab.get("imports", []) if isinstance(n, str)]

    def import_head_lines(self, tab, lang):
        """The import lines a tab's generated code starts with."""
        libs = self.libraries_for(lang)
        lines = libraries.import_lines(libs, self.tab_imports(tab))
        return libraries.with_required(lines, libs, self.tab_required_libraries(tab))

    def tab_required_libraries(self, tab):
        """Libraries that blocks used in the tab ask for ("requires" in the block file)."""
        blocks = self.collect_tab_blocks(tab)
        if blocks is None and getattr(self, "tabs", None) and tab is self.tabs[self.active_tab_index]:
            blocks = self.project_blocks
        names = []
        for block_id, _params in self.iter_all_blocks_recursive(blocks or []):
            for n in get_block_attr(self.blocks.get(block_id), "requires", None) or []:
                if n not in names:
                    names.append(n)
        return names

    # ---- palette search results --------------------------------------------
    def palette_library_section(self, term):
        """Library commands matching the search box, drawn at the top of the palette."""
        if not term.strip() or not getattr(self, "tabs", None):
            return
        lang = self.current_language
        libs = self.libraries_for(lang)
        hits = libraries.search_commands(libs, term, MAX_RESULTS)
        if not hits:
            return
        tab = self.tabs[self.active_tab_index]
        have = set(self.tab_imports(tab))
        head = tk.Frame(self.palette_frame, bg=DARK_PANEL)
        tk.Label(head, text="LIBRARY COMMANDS", bg=DARK_PANEL, fg="#9cdcfe", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Label(head, text=f"({len(hits)})", bg=DARK_PANEL, fg="#666666", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        head.pack(fill=tk.X, pady=(10, 2))
        for lib, command in hits:
            status = libraries.command_status(lib, have, lang)
            LibraryResultItem(self.palette_frame, lib, command, status, self.add_library_command).pack(fill=tk.X, pady=1)

    def add_library_command(self, lib, command):
        """Click on a result: make sure the file imports the library (asking
        first), then add the command as a raw-code block you can edit."""
        tab = self.tabs[self.active_tab_index]
        lang = tab["language"]
        raw_id = self.get_raw_code_block_id(lang)
        param = self.get_raw_code_param_name(raw_id) if raw_id else None
        if not raw_id or not param:
            messagebox.showinfo("Library command", f"There is no raw code block for {lang}, so this can't be added.")
            return
        if lib["name"] not in self.tab_imports(tab):
            status = libraries.command_status(lib, set(), lang)
            text = f'"{command["name"]}" needs this line at the top of the file:\n\n    {lib["import"]}\n\nAdd it and continue?'
            if status == "not_installed":
                text = (f'The library "{lib["name"]}" is not installed on this computer, so the program '
                        f'will fail here until it is (for example with pip).\n\n' + text)
            if not messagebox.askyesno("Add import", text):
                return
            tab.setdefault("imports", []).append(lib["name"])
            self.mark_active_tab_dirty()
        raw_module = self.blocks.get(raw_id)
        self.edit_block_params(raw_module, {param: command["example"] or command["signature"]}, add_mode=True)
        self.update_generated_code()
