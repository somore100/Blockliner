"""File > Apply AI Changes...: paste changes an AI chat suggested (see change_import for the format), look at each
one as a before/after, and apply the ones you want as ONE undoable step."""
import difflib
import tkinter as tk
from tkinter import messagebox

import change_import
import ui_node
from nodes_model import make_node, next_order
from ui_common import BLOCK_BG, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG


class ChangesMixin:

    def open_changes_dialog(self):
        """Paste box + 'Copy instructions for AI' + Preview."""
        dlg = tk.Toplevel(self)
        dlg.title("Apply AI Changes")
        dlg.geometry("720x520")
        dlg.minsize(480, 300)
        dlg.configure(bg=DARK_BG)
        dlg.transient(self)
        tk.Label(dlg, text="Paste the changes your AI suggested. Each one names a function (node) and quotes the code, "
                 "so no line numbers are needed.", bg=DARK_BG, fg="#888888", font=("Segoe UI", 9),
                 wraplength=680, justify="left").pack(side=tk.TOP, anchor="w", padx=10, pady=(10, 4))
        row = tk.Frame(dlg, bg=DARK_BG)
        row.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(4, 10))
        box = tk.Text(dlg, bg=BLOCK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT, wrap=tk.NONE,
                      font=("Consolas", 10), undo=True)
        box.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        status = tk.Label(dlg, text="", bg=DARK_BG, fg="#e0a050", font=("Segoe UI", 9), anchor="w")
        status.pack(side=tk.BOTTOM, fill=tk.X, padx=10)

        def copy_instructions():
            self.clipboard_clear()
            self.clipboard_append(change_import.INSTRUCTIONS)
            status.configure(text="Instructions copied. Paste them into your chat before asking for changes.", fg="#7fbf7f")

        def paste():
            try:
                box.insert(tk.INSERT, self.clipboard_get())
            except tk.TclError:
                pass

        def preview():
            ops, problems = change_import.parse(box.get("1.0", tk.END))
            if not ops:
                status.configure(text=" ".join(problems), fg="#e0a050")
                return
            dlg.destroy()
            self.preview_changes(ops, problems)

        tk.Button(row, text="Copy instructions for AI", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9), command=copy_instructions).pack(side=tk.LEFT)
        tk.Button(row, text="Paste", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9), command=paste).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(row, text="Cancel", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9), command=dlg.destroy).pack(side=tk.RIGHT)
        tk.Button(row, text="Preview changes", bg=DARK_ACCENT, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9, "bold"), command=preview).pack(side=tk.RIGHT, padx=(0, 8))
        dlg._changes_box, dlg._changes_preview = box, preview
        box.focus_set()
        return dlg

    def _change_plan(self, ops):
        self.sync_active_tab_state()
        tab = self.tabs[self.active_tab_index]
        lang = tab["language"]

        def code_of(node):
            with self._language_scope(lang):
                return self.generate_code_for_node(node, lang)

        def locked(node):
            return "it is a window layout node (change it in the designer)" if ui_node.is_ui_node(node) else ""
        return change_import.plan(tab["nodes"], ops, code_of, locked)

    def preview_changes(self, ops, problems=()):
        """One row per change: a tick box and the before/after. Apply puts the ticked ones in."""
        changes = self._change_plan(ops)
        dlg = tk.Toplevel(self)
        dlg.title("Review changes")
        dlg.geometry("760x600")
        dlg.minsize(480, 320)
        dlg.configure(bg=DARK_BG)
        dlg.transient(self)
        row = tk.Frame(dlg, bg=DARK_BG)
        row.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(4, 10))
        text = tk.Text(dlg, bg=BLOCK_BG, fg=DARK_FG, relief=tk.FLAT, wrap=tk.NONE, font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))
        text.tag_configure("head", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        text.tag_configure("add", foreground="#7fd37f")
        text.tag_configure("del", foreground="#e07070")
        text.tag_configure("bad", foreground="#e0a050")
        vars_ = []
        for n, ch in enumerate(changes, 1):
            var = tk.BooleanVar(value=ch.ok)
            vars_.append(var)
            label = {"edit": "Edit", "replace": "Replace", "new": "New node"}[ch.op.kind]
            cb = tk.Checkbutton(text, text=f"{n}. {label}: {ch.op.node}", variable=var, bg=BLOCK_BG, fg="#ffffff",
                                selectcolor=DARK_BG, activebackground=BLOCK_BG, font=("Segoe UI", 10, "bold"),
                                state=tk.NORMAL if ch.ok else tk.DISABLED, anchor="w")
            text.window_create(tk.END, window=cb)
            text.insert(tk.END, "\n")
            if not ch.ok:
                text.insert(tk.END, f"   Can't apply: {ch.error}\n\n", "bad")
                continue
            for ln in difflib.unified_diff(ch.old.splitlines(), ch.new.splitlines(), lineterm="", n=2):
                if ln.startswith(("---", "+++")):
                    continue
                text.insert(tk.END, ln + "\n", "add" if ln.startswith("+") and not ln.startswith("@@") else
                            "del" if ln.startswith("-") else ())
            if ch.op.kind == "new":
                for ln in ch.new.splitlines():
                    text.insert(tk.END, "+" + ln + "\n", "add")
            text.insert(tk.END, "\n")
        for p in problems:
            text.insert(tk.END, f"Skipped: {p}\n", "bad")
        text.configure(state=tk.DISABLED)

        def apply_selected():
            chosen = [c for c, v in zip(changes, vars_) if v.get() and c.ok]
            if not chosen:
                return
            dlg.destroy()
            self.apply_changes(chosen)
        ok_count = sum(1 for c in changes if c.ok)
        tk.Button(row, text="Close", bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9), command=dlg.destroy).pack(side=tk.RIGHT)
        dlg._apply_btn = tk.Button(
            row, text=f"Apply ticked ({ok_count})", bg=DARK_ACCENT, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), state=tk.NORMAL if ok_count else tk.DISABLED, command=apply_selected)
        dlg._apply_btn.pack(side=tk.RIGHT, padx=(0, 8))
        dlg._changes, dlg._change_vars, dlg._apply = changes, vars_, apply_selected
        return dlg

    def apply_changes(self, changes):
        """Put the checked changes into the active file as one undoable step. Returns how many were applied."""
        self.sync_active_tab_state()
        tab = self.tabs[self.active_tab_index]
        lang = tab["language"]
        if self.get_raw_code_block_id(lang) is None:
            messagebox.showerror("Can't Apply", f"No Raw Code block for '{lang}', so code can't be turned into blocks.")
            return 0
        names = [c.op.node for c in changes]
        self.record_project_undo("AI changes: " + ", ".join(names[:3]) + (f" (+{len(names) - 3} more)" if len(names) > 3 else ""))
        for ch in changes:
            with self._language_scope(lang):
                blocks = self.import_code_to_blocks(ch.new)[0]
            if ch.node is None:
                tab["nodes"].append(make_node(ch.op.node.rpartition(".")[2], node_id=self._new_change_id(tab),
                                              blocks=blocks, order=next_order(tab["nodes"])))
            else:
                ch.node["blocks"] = blocks
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()
        self.show_change_bar(f"Applied {len(changes)} AI change(s): " + ", ".join(names[:3]) + ("..." if len(names) > 3 else ""))
        return len(changes)

    def _new_change_id(self, tab):
        import uuid
        return str(uuid.uuid4())[:8]
