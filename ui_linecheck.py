"""Free-writing check in the code panel: a gutter marker per line and a bulb
that explains a doubtful line and offers the fix. The judging itself is pure
(line_check.py); this file only shows it. Nothing is ever changed without a click.

    green dot      the line fits a block
    amber bulb     probably a typo: click for what is wrong and the fix
    grey ring      Blockliner has no block for it, so it stays raw code
"""
import tkinter as tk

import libraries
import line_check
import portable
from ui_common import DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL

KNOWN_COLOR = "#4caf50"
TYPO_COLOR = "#e5a50a"
RAW_COLOR = "#808080"
GUTTER_WIDTH = 22
MAX_CHECKED_LINES = 4000
DEFAULT_SENSITIVITY = 70      # percent: lowest name similarity still called a typo


class LineCheckMixin:

    def install_line_check(self):
        self._lc_after = None
        self._lc_results = {}          # line number -> Check
        self._lc_cache = None          # ((lang, block count), matchers, words)
        self.code_gutter = tk.Canvas(self.code_text.master, width=GUTTER_WIDTH, bg=DARK_BG, highlightthickness=0)
        self.code_gutter.pack(side=tk.LEFT, fill=tk.Y, pady=10, before=self.code_text)
        self.code_text.tag_configure("lc_typo", foreground=TYPO_COLOR, underline=True)
        for seq in ("<KeyRelease>", "<ButtonRelease-1>", "<MouseWheel>", "<Button-4>", "<Button-5>", "<Configure>"):
            self.code_text.bind(seq, lambda _e: self.schedule_line_check(), add="+")
        self.code_gutter.bind("<Button-1>", self._lc_gutter_click)
        self.schedule_line_check()

    # ---- settings -----------------------------------------------------------
    def line_check_enabled(self):
        return bool(self.settings.get("line_check", True))

    def typo_threshold(self):
        try:
            percent = int(self.settings.get("typo_sensitivity", DEFAULT_SENSITIVITY))
        except (TypeError, ValueError):
            percent = DEFAULT_SENSITIVITY
        return max(50, min(95, percent)) / 100.0

    # ---- scheduling -----------------------------------------------------------
    def schedule_line_check(self, delay_ms=250):
        if getattr(self, "_lc_after", None) is not None:
            try:
                self.after_cancel(self._lc_after)
            except tk.TclError:
                pass
        self._lc_after = self.after(delay_ms, self.run_line_check)

    def _lc_vocabulary(self):
        """(matchers, words) for the current language, rebuilt when the block set changes."""
        lang = self.current_language
        key = (lang, len(self.blocks))
        if self._lc_cache is None or self._lc_cache[0] != key:
            patterns = list(self.build_reverse_patterns(lang)) + list(self.build_container_header_patterns(lang))
            words = line_check.language_words(lang)
            for pat in patterns:
                words |= line_check.words_from_pattern(pat["regex"].pattern)
            self._lc_cache = (key, [p["regex"] for p in patterns], words)
        return self._lc_cache[1], self._lc_cache[2]

    def run_line_check(self):
        self._lc_after = None
        self.code_text.tag_remove("lc_typo", "1.0", "end")
        self.code_gutter.delete("all")
        self._lc_results = {}
        if not self.line_check_enabled() or not getattr(self, "tabs", None):
            return
        lines = self.code_text.get("1.0", "end-1c").split("\n")
        if len(lines) > MAX_CHECKED_LINES:
            return
        matchers, words = self._lc_vocabulary()
        tab = self.tabs[self.active_tab_index]
        words = words | {n["name"] for n, _p in self.iter_tab_nodes(tab) if n.get("name")}
        libs = self.libraries_for(tab["language"])
        words = words | {c["use"] for lib in libs.values() for c in lib["commands"] if c["use"].isidentifier()}
        lib_info = {"index": libraries.qualified_index(libs),
                    "imported": set(self.tab_imports(tab)) | set(libraries.imported_names(libs, lines))}
        checks = line_check.analyse_text(lines, matchers, words, set(self.settings.get("code_ignored_words", [])),
                                         self.typo_threshold(), lib_info if lib_info["index"] else None)
        skip = portable.protected_line_numbers(lines)
        for number, check in enumerate(checks, 1):
            if number in skip or check.state == line_check.NONE:
                continue
            self._lc_results[number] = check
            if check.state in (line_check.TYPO, line_check.IMPORT):
                self.code_text.tag_add("lc_typo", f"{number}.{check.start}", f"{number}.{check.end}")
        self.draw_line_gutter()

    # ---- drawing --------------------------------------------------------------
    def draw_line_gutter(self):
        gutter = self.code_gutter
        gutter.delete("all")
        for number, check in self._lc_results.items():
            box = self.code_text.dlineinfo(f"{number}.0")
            if box is None:
                continue
            y = box[1] + box[3] / 2
            x = GUTTER_WIDTH / 2
            if check.state == line_check.KNOWN:
                gutter.create_oval(x - 3, y - 3, x + 3, y + 3, fill=KNOWN_COLOR, outline="", tags=(f"line{number}",))
            elif check.state == line_check.UNVERIFIED:
                gutter.create_oval(x - 3, y - 3, x + 3, y + 3, outline=RAW_COLOR, width=1, tags=(f"line{number}",))
            else:
                gutter.create_oval(x - 7, y - 7, x + 7, y + 7, fill=TYPO_COLOR, outline="", tags=(f"line{number}",))
                gutter.create_text(x, y, text="!", fill="#1e1e1e", font=("Segoe UI", 9, "bold"), tags=(f"line{number}",))

    def _lc_gutter_click(self, event):
        for item in self.code_gutter.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4):
            for tag in self.code_gutter.gettags(item):
                if tag.startswith("line"):
                    self.show_line_bulb(int(tag[4:]), event.x_root, event.y_root)
                    return

    # ---- the bulb ---------------------------------------------------------------
    def show_line_bulb(self, number, x_root, y_root):
        check = self._lc_results.get(number)
        if check is None or check.state == line_check.KNOWN:
            return
        old = getattr(self, "_lc_bulb", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        win = tk.Toplevel(self)
        self._lc_bulb = win
        win.title("Check this line")
        win.configure(bg=DARK_PANEL)
        win.transient(self)
        win.geometry(f"+{int(x_root) + 12}+{int(y_root) - 10}")
        line = self.code_text.get(f"{number}.0", f"{number}.end")
        tk.Label(win, text=f"Line {number}:  {line.strip()}", bg=DARK_PANEL, fg=DARK_FG, anchor="w",
                 font=("Consolas", 9)).pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(win, text=line_check.describe(check), bg=DARK_PANEL, fg=RAW_COLOR if check.state == line_check.UNVERIFIED else TYPO_COLOR,
                 anchor="w", justify=tk.LEFT, wraplength=360, font=("Segoe UI", 9)).pack(fill=tk.X, padx=12, pady=(0, 8))

        def button(text, command):
            tk.Button(win, text=text, command=command, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                      activebackground=DARK_BORDER, activeforeground=DARK_FG, font=("Segoe UI", 9),
                      anchor="w", padx=8).pack(fill=tk.X, padx=12, pady=2)

        if check.state == line_check.TYPO:
            for name, score in check.suggestions:
                label = f'Fix: remove "{check.word}"' if name == "" else f'Fix: change "{check.word}" to "{name}"'
                button(f"{label}  ({round(score * 100)}%)", lambda n=name: self._lc_apply_fix(number, check, n, win))
            button(f'Keep "{check.word}" as it is', lambda: self._lc_keep_word(check.word, win))
        if check.state == line_check.IMPORT:
            lib_name = check.action[1]
            lib = self.libraries_for(self.tabs[self.active_tab_index]["language"]).get(lib_name)
            button(f'Add import: {lib["import"] if lib else lib_name}', lambda: self._lc_add_import(lib_name, win))
        button("Close", win.destroy)
        win.bind("<Escape>", lambda _e: win.destroy())
        tk.Frame(win, bg=DARK_PANEL, height=8).pack()

    def _lc_apply_fix(self, number, check, replacement, win):
        """Replace just the doubtful word, through the normal edit path, so the
        usual code -> blocks sync picks it up."""
        line = self.code_text.get(f"{number}.0", f"{number}.end")
        if line[check.start:check.end] != check.word:       # the line changed since it was checked
            win.destroy()
            self.schedule_line_check(0)
            return
        self.code_text.delete(f"{number}.{check.start}", f"{number}.{check.end}")
        if replacement:
            self.code_text.insert(f"{number}.{check.start}", replacement)
        win.destroy()
        self.schedule_line_check(0)

    def _lc_add_import(self, lib_name, win):
        """The bulb's fix for a library used without its import."""
        tab = self.tabs[self.active_tab_index]
        if lib_name not in self.tab_imports(tab):
            tab["imports"] = self.tab_imports(tab) + [lib_name]
            self.mark_active_tab_dirty()
        win.destroy()
        self.update_generated_code()

    def _lc_keep_word(self, word, win):
        """Remember that this word is meant (stored in settings, per user)."""
        kept = list(self.settings.get("code_ignored_words", []))
        if word not in kept:
            kept.append(word)
        self.settings["code_ignored_words"] = kept
        self.save_app_settings()
        win.destroy()
        self.schedule_line_check(0)
