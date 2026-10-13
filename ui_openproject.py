"""File > Open project...: pick a folder, list its files, import them into the
current workspace (each file becomes a file tab). See project_scan."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox

import portable
import project_scan
from ui_common import (BLOCK_BG, DARK_ACCENT, DARK_BG, DARK_FG, LANGUAGE_EXTENSIONS)


class OpenProjectMixin:
    def open_project_dialog(self, folder=None):
        """Ask for a folder (unless given), scan it, show the list dialog."""
        if folder is None:
            folder = filedialog.askdirectory(title="Open project - pick the project's root folder")
        if not folder:
            return None
        entries, truncated = project_scan.scan_folder(folder, LANGUAGE_EXTENSIONS)
        return self._show_project_dialog(folder, entries, truncated)

    # ---- importing -----------------------------------------------------
    def import_project_file(self, entry, split):
        """Import one scanned entry as a new file in the current workspace.
        split=True: nodes by top-level code (portable.split_top_level);
        False: the whole file as one node. Returns diagnostics or None."""
        if not entry.get("ok"):
            return None
        lang = entry["language"]
        if not os.path.isdir(os.path.join(self.languages_path, lang)):
            return None
        try:
            text = project_scan.read_text(entry["path"])
        except OSError:
            return None
        token = self.get_comment_token(lang) or "#"
        chunks = portable.split_top_level(text) if split else []
        if not chunks:
            stem = os.path.splitext(os.path.basename(entry["rel"]))[0]
            chunks = [(stem or "main", text)]
        marked = portable.wrap_with_markers(chunks, token)
        return self.load_portable_text(marked, title=project_scan.node_title(entry["rel"]),
                                       language=lang)

    def import_project_files(self, entries, split):
        """Import several; ends on the Files layer. Returns how many opened."""
        done = 0
        for e in entries:
            if self.import_project_file(e, split) is not None:
                done += 1
        if done:
            self.goto_layer("files")
        return done

    # ---- dialog ---------------------------------------------------------
    def _show_project_dialog(self, folder, entries, truncated):
        dlg = tk.Toplevel(self)
        dlg.title("Open project")
        dlg.geometry("720x520")
        dlg.configure(bg=DARK_BG)
        dlg.transient(self)
        dlg._entries = entries
        dlg._split = None            # asked once per dialog, then remembered
        dlg._imported = set()
        dlg._row_buttons = {}
        ok_entries = [e for e in entries if e["ok"]]
        head = f"{os.path.basename(os.path.abspath(folder)) or folder}   -   {len(entries)} files, {len(ok_entries)} can be imported"
        if truncated:
            head += f"  (only the first {project_scan.MAX_FILES} are listed)"
        tk.Label(dlg, text=head, bg=DARK_BG, fg=DARK_FG, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill=tk.X, padx=10, pady=(10, 2))
        tk.Label(dlg, text="Click ↑ to import a file into the current workspace as a file tab.",
                 bg=DARK_BG, fg="#888888", font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=10)

        body = tk.Frame(dlg, bg=DARK_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        canvas = tk.Canvas(body, bg=BLOCK_BG, highlightthickness=0)
        sb = tk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BLOCK_BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120 or (1 if e.delta > 0 else -1)), "units"))
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))

        for i, e in enumerate(entries):
            fg = DARK_FG if e["ok"] else "#666666"
            btn = tk.Button(inner, text="↑", width=3, relief=tk.FLAT, cursor="hand2" if e["ok"] else "",
                            bg=DARK_ACCENT if e["ok"] else "#2a2a2a", fg="#ffffff" if e["ok"] else "#555555",
                            state=tk.NORMAL if e["ok"] else tk.DISABLED,
                            command=lambda e=e: self._project_dialog_import(dlg, [e]))
            btn.grid(row=i, column=0, padx=(4, 8), pady=1, sticky="w")
            dlg._row_buttons[e["rel"]] = btn
            tk.Label(inner, text=e["rel"], bg=BLOCK_BG, fg=fg, anchor="w",
                     font=("Consolas", 10)).grid(row=i, column=1, sticky="w")
            info = e["language"] if e["ok"] else e["reason"]
            tk.Label(inner, text=f"   {info}   {_size_text(e['size'])}", bg=BLOCK_BG, fg="#777777",
                     anchor="w", font=("Segoe UI", 9)).grid(row=i, column=2, sticky="w", padx=(8, 4))

        row = tk.Frame(dlg, bg=DARK_BG)
        row.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Button(row, text="Close", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  command=dlg.destroy).pack(side=tk.RIGHT)
        dlg._import_all_btn = tk.Button(
            row, text=f"↑ Import all ({len(ok_entries)})", bg=DARK_ACCENT, fg="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9, "bold"),
            state=tk.NORMAL if ok_entries else tk.DISABLED,
            command=lambda: self._project_dialog_import(dlg, ok_entries))
        dlg._import_all_btn.pack(side=tk.RIGHT, padx=(0, 8))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        return dlg

    def _project_dialog_import(self, dlg, entries):
        todo = [e for e in entries if e["rel"] not in dlg._imported]
        if not todo:
            return 0
        if dlg._split is None:
            dlg._split = bool(messagebox.askyesno(
                "Split into nodes?",
                "Split the imported files into nodes automatically?\n\n"
                "Yes = every top-level class / function / block of code becomes its own node "
                "(runs of plain top-level lines become one 'top_level' node).\n"
                "No = each file becomes a single node.",
                parent=dlg))
        n = self.import_project_files(todo, dlg._split)
        for e in todo:
            dlg._imported.add(e["rel"])
            b = dlg._row_buttons.get(e["rel"])
            if b is not None:
                b.configure(text="✓", state=tk.DISABLED, bg="#2a2a2a")
        return n


def _size_text(n):
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB"
