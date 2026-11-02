"""Imports manager window (Tools > Imports...): tick libraries for the current
file, browse what each offers, apply a preset, and tidy the file's imports.
The rules are pure (libraries.py); this file only shows them and applies the
fixes you click. Nothing is changed without a click."""
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import libraries
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL

OK_COLOR, WARN_COLOR, BAD_COLOR = "#4caf50", "#e5a50a", "#d9534f"


class ImportManagerMixin:

    def user_presets_path(self, lang):
        return os.path.join(os.path.dirname(APP_SETTINGS_PATH), f"import_presets_{lang}.json")

    def presets_for(self, lang):
        return libraries.load_presets(os.path.join(self.languages_path, lang, "presets.json"), self.user_presets_path(lang))

    def show_import_manager(self):
        existing = getattr(self, "_imports_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        tab = self.tabs[self.active_tab_index]
        lang = tab["language"]
        libs = self.libraries_for(lang)
        if not libs:
            messagebox.showinfo("Imports", f"There are no libraries for {lang} yet.\n\n"
                                           f"Add JSON files to languages/{lang}/libraries/.")
            return None
        win = tk.Toplevel(self)
        self._imports_win = win
        win.title("Imports")
        win.configure(bg=DARK_PANEL)
        win.geometry("820x600")
        win.minsize(640, 460)
        win.transient(self)
        ticks = {}                         # library name -> BooleanVar
        state = {"selected": next(iter(libs))}

        def label(parent, text, **kw):
            return tk.Label(parent, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w",
                            font=kw.pop("font", ("Segoe UI", 9)), **kw)

        def button(parent, text, command):
            return tk.Button(parent, text=text, command=command, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
                             cursor="hand2", activebackground=DARK_BORDER, activeforeground=DARK_FG,
                             font=("Segoe UI", 9), padx=8)

        def file_name():
            return tab.get("title") or "this file"

        label(win, f"Imports for {file_name()}  ({lang})", font=("Segoe UI", 11, "bold")).pack(fill=tk.X, padx=14, pady=(12, 2))
        label(win, "Ticked libraries are imported at the top of this file's code.", fg="#888888").pack(fill=tk.X, padx=14)

        # ---- presets row ------------------------------------------------------
        row = tk.Frame(win, bg=DARK_PANEL)
        row.pack(fill=tk.X, padx=14, pady=(10, 4))
        label(row, "Preset:").pack(side=tk.LEFT)
        preset_var = tk.StringVar()
        combo = ttk.Combobox(row, textvariable=preset_var, state="readonly", width=24)
        combo.pack(side=tk.LEFT, padx=6)

        def refresh_presets():
            combo["values"] = [p["name"] for p in self.presets_for(lang)]
        refresh_presets()

        def chosen_preset():
            return next((p for p in self.presets_for(lang) if p["name"] == preset_var.get()), None)

        def apply_preset(all_files=False):
            preset = chosen_preset()
            if preset is None:
                return
            names, unknown = libraries.preset_libraries(preset, libs)
            targets = [t for t in self.tabs if t["language"] == lang] if all_files else [tab]
            for t in targets:
                have = self.tab_imports(t)
                t["imports"] = have + [n for n in names if n not in have]
                t["dirty"] = True
            if unknown:
                messagebox.showinfo("Preset", "These libraries aren't available for this language and were skipped:\n" + ", ".join(unknown), parent=win)
            changed()

        def save_preset():
            chosen = [n for n, v in ticks.items() if v.get()]
            if not chosen:
                messagebox.showinfo("Preset", "Tick the libraries you want in the preset first.", parent=win)
                return
            name = simpledialog.askstring("Save preset", "Name for this preset:", parent=win)
            if not name or not name.strip():
                return
            if libraries.save_preset(self.user_presets_path(lang), name.strip(), chosen):
                refresh_presets()
                preset_var.set(name.strip())
            else:
                messagebox.showwarning("Preset", "The preset could not be saved.", parent=win)

        button(row, "Apply here", apply_preset).pack(side=tk.LEFT, padx=2)
        button(row, "Apply to all files", lambda: apply_preset(True)).pack(side=tk.LEFT, padx=2)
        button(row, "Save ticks as preset...", save_preset).pack(side=tk.RIGHT)

        # ---- libraries + commands -----------------------------------------------
        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)
        left = tk.Frame(body, bg=DARK_BG, width=230)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        right = tk.Frame(body, bg=DARK_PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        detail_title = label(right, "", font=("Segoe UI", 10, "bold"))
        detail_title.pack(fill=tk.X)
        detail_line = label(right, "", fg="#9cdcfe", font=("Consolas", 9))
        detail_line.pack(fill=tk.X)
        detail_note = label(right, "", fg="#888888", wraplength=480, justify=tk.LEFT)
        detail_note.pack(fill=tk.X, pady=(2, 6))
        commands = tk.Listbox(right, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, highlightthickness=0, font=("Consolas", 9),
                              selectbackground=DARK_ACCENT, activestyle="none")
        commands.pack(fill=tk.BOTH, expand=True)
        command_help = label(right, "", fg="#888888", wraplength=480, justify=tk.LEFT)
        command_help.pack(fill=tk.X, pady=(4, 0))

        def show_library(name):
            state["selected"] = name
            lib = libs[name]
            detail_title.config(text=lib["name"])
            detail_line.config(text=lib["import"])
            inst = libraries.installed(lib, lang)
            note = lib["description"]
            if inst is False:
                note += "\nNot installed on this computer."
            detail_note.config(text=note, fg=BAD_COLOR if inst is False else "#888888")
            commands.delete(0, tk.END)
            for c in lib["commands"]:
                commands.insert(tk.END, c["signature"])
            command_help.config(text="Select a command to see what it does.")

        def on_command(_e=None):
            sel = commands.curselection()
            if sel:
                c = libs[state["selected"]]["commands"][sel[0]]
                command_help.config(text=c["does"] or c["signature"])
        commands.bind("<<ListboxSelect>>", on_command)

        def toggle(name):
            have = self.tab_imports(tab)
            if ticks[name].get() and name not in have:
                have.append(name)
            elif not ticks[name].get() and name in have:
                have.remove(name)
            tab["imports"] = have
            tab["dirty"] = True
            changed()

        for name, lib in libs.items():
            ticks[name] = tk.BooleanVar(value=name in self.tab_imports(tab))
            item = tk.Frame(left, bg=DARK_BG)
            item.pack(fill=tk.X)
            tk.Checkbutton(item, variable=ticks[name], command=lambda n=name: toggle(n), bg=DARK_BG, activebackground=DARK_BG,
                           selectcolor=DARK_PANEL).pack(side=tk.LEFT)
            name_label = tk.Label(item, text=name, bg=DARK_BG, fg=DARK_FG, anchor="w", cursor="hand2", font=("Segoe UI", 9))
            name_label.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=3)
            name_label.bind("<Button-1>", lambda _e, n=name: show_library(n))
        show_library(state["selected"])

        # ---- tidy ----------------------------------------------------------------
        tidy_box = tk.Frame(win, bg=DARK_PANEL)
        tidy_box.pack(fill=tk.X, padx=14, pady=(4, 12))
        head = tk.Frame(tidy_box, bg=DARK_PANEL)
        head.pack(fill=tk.X)
        label(head, "Tidy imports", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        findings = tk.Frame(tidy_box, bg=DARK_PANEL)
        findings.pack(fill=tk.X, pady=(4, 0))

        def tidy_items():
            """[(text, colour, fix label, fix function)] for this file."""
            code_lines = self.generate_code_for_tab(tab, lang).split("\n")
            report = libraries.tidy_report(libs, code_lines)
            items = []
            raw_id = self.get_raw_code_block_id(lang)
            raw_param = self.get_raw_code_param_name(raw_id) if raw_id else None
            typed = []
            if raw_id and raw_param:
                for node, _path in self.iter_tab_nodes(tab):
                    for index, name in libraries.raw_import_blocks(libs, node.get("blocks", []), raw_id, raw_param):
                        typed.append((node, index, name))
            for name in report["missing"]:
                if any(t[2] == name for t in typed):
                    continue
                by = libraries.used_by(libs[name], code_lines)
                items.append((f'Missing: "{name}" is used ({by}) but not imported.', WARN_COLOR, "Add import",
                              lambda n=name: self._tidy_add(tab, n)))
            for name in report["unused"]:
                if name in self.tab_imports(tab):
                    items.append((f'Unused: "{name}" is imported but nothing from it is used.', WARN_COLOR, "Remove",
                                  lambda n=name: self._tidy_remove(tab, n)))
            done = set()
            for node, index, name in typed:
                if (id(node), name) in done:
                    continue
                done.add((id(node), name))
                items.append((f'Typed by hand: "{libs[name]["import"]}" in node "{node.get("name", "?")}" - move it to the managed imports.',
                              WARN_COLOR, "Move", lambda nd=node, n=name: self._tidy_adopt(tab, nd, n, raw_id, raw_param, libs)))
            return items

        def show_tidy():
            for w in findings.winfo_children():
                w.destroy()
            items = tidy_items()
            if not items:
                label(findings, "✓ Nothing to tidy.", fg=OK_COLOR).pack(fill=tk.X)
                return
            for text, color, fix_label, fix in items:
                line = tk.Frame(findings, bg=DARK_PANEL)
                line.pack(fill=tk.X, pady=1)
                label(line, text, fg=color, wraplength=640, justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X, expand=True)
                button(line, fix_label, lambda f=fix: (f(), changed())).pack(side=tk.RIGHT)
            if len(items) > 1:
                button(findings, "Fix all", lambda: ([f() for _t, _c, _l, f in items], changed())).pack(anchor="e", pady=(4, 0))

        def changed():
            """A change was made: show it in the code and redo the lists."""
            for name, var in ticks.items():
                var.set(name in self.tab_imports(tab))
            self.mark_active_tab_dirty()
            self.refresh_workspace()
            self.update_generated_code()
            show_tidy()

        button(head, "Check again", show_tidy).pack(side=tk.RIGHT)
        show_tidy()
        win.bind("<Escape>", lambda _e: win.destroy())
        return win

    # ---- tidy fixes (each one a small, visible change) ----------------------------
    def _tidy_add(self, tab, name):
        have = self.tab_imports(tab)
        if name not in have:
            tab["imports"] = have + [name]

    def _tidy_remove(self, tab, name):
        tab["imports"] = [n for n in self.tab_imports(tab) if n != name]

    def _tidy_adopt(self, tab, node, name, raw_id, raw_param, libs):
        """Drop the hand-typed import block(s) of a library and manage it instead."""
        blocks = node.get("blocks", [])
        drop = {i for i, n in libraries.raw_import_blocks(libs, blocks, raw_id, raw_param) if n == name}
        blocks[:] = [b for i, b in enumerate(blocks) if i not in drop]     # in place: the open node shares this list
        self._tidy_add(tab, name)
