"""The "How is a project built?" window: a file holds nodes, a node holds blocks, a block is one line of
code. Drawn as nested boxes next to the code they make, with a button per level that takes you to its layer."""
import tkinter as tk

import structure_help as SH
from ui_common import DARK_BG, DARK_FG, DARK_PANEL


class StructureMixin:

    def show_structure_help(self):
        existing = self.__dict__.get("_structure_win")
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        win = tk.Toplevel(self)
        self._structure_win = win
        win.title("How is a project built?")
        win.configure(bg=DARK_PANEL)
        win.geometry("900x600")
        win.minsize(700, 480)
        win.transient(self)
        win.bind("<Escape>", lambda _e: win.destroy())
        by_key = {lv["key"]: lv for lv in SH.LEVELS}

        tk.Label(win, text="How is a project built?", bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 13, "bold"),
                 anchor="w").pack(fill=tk.X, padx=18, pady=(14, 0))
        tk.Label(win, text="Big to small: a file holds nodes, a node holds blocks, and a block is one line of code.",
                 bg=DARK_PANEL, fg="#aaaaaa", font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=18, pady=(0, 8))

        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=18)
        left = tk.Frame(body, bg=DARK_PANEL)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(body, bg=DARK_PANEL)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        # ---- nested boxes: file > node > block
        def box(parent, level, title, pad):
            lv = by_key[level]
            outer = tk.Frame(parent, bg=lv["color"], bd=0)
            outer.pack(fill=tk.X, padx=pad, pady=3)
            inner = tk.Frame(outer, bg=DARK_BG)
            inner.pack(fill=tk.BOTH, padx=2, pady=2)
            tk.Label(inner, text=f"{lv['icon']} {lv['name']}  {title}", bg=DARK_BG, fg=lv["color"],
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, padx=8, pady=(4, 2))
            return inner

        tk.Label(left, text="What you build", bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
        file_box = box(left, "file", f"— {SH.FILE_NAME}", 0)
        for number, (name, blocks) in enumerate(SH.EXAMPLE, 1):
            node_box = box(file_box, "node", f"{number} — {name}", 8)
            for text, depth in blocks:
                row = tk.Frame(node_box, bg=DARK_BG)
                row.pack(fill=tk.X, padx=(10 + 22 * depth, 8), pady=1)
                tk.Label(row, text="\U0001F9E9", bg=DARK_BG, font=("Segoe UI", 8)).pack(side=tk.LEFT)
                tk.Label(row, text=text, bg="#2d2d30", fg=DARK_FG, font=("Consolas", 9), anchor="w", padx=6).pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Frame(node_box, bg=DARK_BG, height=3).pack()

        # ---- the code it makes, banded per node
        tk.Label(right, text="What Blockliner writes (Code layer)", bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
        code = tk.Text(right, bg=DARK_BG, fg=DARK_FG, font=("Consolas", 9), relief=tk.FLAT, padx=8, pady=8, wrap=tk.NONE, height=18, width=44)
        code.pack(fill=tk.BOTH, expand=True, pady=3)
        names = [n for n, _ in SH.EXAMPLE]
        for index, name in enumerate(names):
            code.tag_config(f"node{index}", background="#3a3224" if index % 2 == 0 else "#2a2a22")
        code.tag_config("marker", foreground="#777777")
        for name, line in SH.code_rows():
            tags = (f"node{names.index(name)}", "marker") if line.lstrip().startswith("# $$$") else (f"node{names.index(name)}",)
            code.insert(tk.END, line + "\n", tags)
        code.config(state=tk.DISABLED)
        tk.Label(right, text="The grey lines are the markers that remember where each node starts and ends; "
                             "the shaded bands are the nodes.", bg=DARK_PANEL, fg="#888888", font=("Segoe UI", 9),
                 anchor="w", justify=tk.LEFT, wraplength=380).pack(fill=tk.X)

        # ---- one row per level, with a way to go there
        legend = tk.Frame(win, bg=DARK_PANEL)
        legend.pack(fill=tk.X, padx=18, pady=(10, 14))

        def go(layer):
            win.destroy()
            self.goto_layer(layer)

        for lv in SH.LEVELS:
            row = tk.Frame(legend, bg=DARK_PANEL)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"{lv['icon']} {lv['name']}", bg=DARK_PANEL, fg=lv["color"], font=("Segoe UI", 10, "bold"),
                     width=9, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=lv["what"], bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9), anchor="w", justify=tk.LEFT,
                     wraplength=600).pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Button(row, text=f"Show me: {lv['where']}", command=lambda k=lv["layer"]: go(k), bg=DARK_BG, fg=DARK_FG,
                      relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9), padx=8).pack(side=tk.RIGHT)
        return win
