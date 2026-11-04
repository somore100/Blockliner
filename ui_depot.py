"""The depot window (Extensions > Depot...): packages in the depot folder that
can be installed or updated. The rules are pure (depot.py); this file only shows
them. Installing copies files and leaves the extension OFF; turning it on in the
manager still asks about its permissions."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import depot
import extensions as X
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL

OK_COLOR, WARN_COLOR, BAD_COLOR = "#4caf50", "#e5a50a", "#d9534f"
STATUS_LABEL = {"new": "Not installed", "installed": "Installed", "update": "Update available",
                "older": "Older than installed", "incompatible": "Incompatible"}


class DepotMixin:

    def depot_dir(self):
        """<data folder>/depot, next to user_data/."""
        return os.path.join(os.path.dirname(os.path.dirname(APP_SETTINGS_PATH)), "depot")

    def _installed_versions(self):
        return {e["manifest"]["id"]: e["manifest"]["extension_version"] for e in self._ext_all if e["manifest"]}

    def _open_folder(self, path):
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)                     # noqa: S606 - the user's own folder
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            messagebox.showinfo("Depot", f"Could not open the folder:\n{path}\n\n{e}")

    def show_depot(self):
        existing = getattr(self, "_depot_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        win = tk.Toplevel(self)
        self._depot_win = win
        win.title("Extension depot")
        win.configure(bg=DARK_PANEL)
        win.geometry("760x460")
        win.minsize(600, 360)
        win.transient(self)
        folder = self.depot_dir()
        user_root = self.extension_roots()[1][0]
        packages = []

        def label(parent, text, **kw):
            return tk.Label(parent, text=text, bg=DARK_PANEL, fg=kw.pop("fg", DARK_FG), anchor="w",
                            font=kw.pop("font", ("Segoe UI", 9)), **kw)

        def button(parent, text, command):
            return tk.Button(parent, text=text, command=command, bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                             activebackground=DARK_BORDER, activeforeground=DARK_FG, font=("Segoe UI", 9), padx=8)

        label(win, "Extension depot", font=("Segoe UI", 12, "bold")).pack(fill=tk.X, padx=14, pady=(12, 0))
        label(win, f"Put extension packages (a folder or a .zip with an extension.json) in:\n{folder}",
              fg="#888888", justify=tk.LEFT).pack(fill=tk.X, padx=14, pady=(0, 8))
        body = tk.Frame(win, bg=DARK_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=14)
        table = ttk.Treeview(body, columns=("name", "version", "status"), show="headings", height=10, selectmode="browse")
        for name, text, width in (("name", "Extension", 230), ("version", "Version", 70), ("status", "Status", 130)):
            table.heading(name, text=text)
            table.column(name, width=width, anchor="w")
        table.pack(side=tk.LEFT, fill=tk.Y)
        detail = tk.Frame(body, bg=DARK_PANEL)
        detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        bar = tk.Frame(win, bg=DARK_PANEL)
        bar.pack(fill=tk.X, padx=14, pady=10)

        def selected():
            sel = table.selection()
            return packages[int(sel[0])] if sel else None

        def show_detail(_e=None):
            for w in detail.winfo_children():
                w.destroy()
            p = selected()
            install_button.configure(state=tk.DISABLED)
            if p is None:
                return
            m = p["manifest"]
            if m is None:
                label(detail, "This package can't be used:", fg=BAD_COLOR).pack(fill=tk.X)
                for note in p["notes"]:
                    label(detail, note, wraplength=380, justify=tk.LEFT, fg="#888888").pack(fill=tk.X)
                return
            st = depot.status(m, self._installed_versions())
            label(detail, f"{m['name']}  {m['extension_version']}", font=("Segoe UI", 11, "bold")).pack(fill=tk.X)
            label(detail, STATUS_LABEL[st], fg={"new": OK_COLOR, "update": OK_COLOR}.get(st, "#888888")).pack(fill=tk.X)
            if m["author"]:
                label(detail, f"by {m['author']}", fg="#888888").pack(fill=tk.X)
            if m["description"]:
                label(detail, m["description"], wraplength=380, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 0))
            label(detail, "It asks for:", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, pady=(8, 0))
            for perm in m["permissions"] or []:
                label(detail, f"• {X.PERMISSIONS[perm]}", wraplength=380, justify=tk.LEFT).pack(fill=tk.X)
            if not m["permissions"]:
                label(detail, "(nothing)").pack(fill=tk.X)
            if st == "incompatible":
                label(detail, X.compatibility(m)[1], fg=BAD_COLOR, wraplength=380, justify=tk.LEFT).pack(fill=tk.X, pady=(6, 0))
            if st in ("new", "update"):
                install_button.configure(text="Update" if st == "update" else "Install", state=tk.NORMAL)

        def refresh():
            packages[:] = depot.scan(folder)
            table.delete(*table.get_children())
            installed = self._installed_versions()
            for i, p in enumerate(packages):
                m = p["manifest"]
                if m is None:
                    table.insert("", tk.END, iid=str(i), values=(os.path.basename(p["path"]), "", "Damaged"))
                else:
                    table.insert("", tk.END, iid=str(i), values=(m["name"], m["extension_version"],
                                                                 STATUS_LABEL[depot.status(m, installed)]))
            if packages:
                table.selection_set("0")
            show_detail()

        def install():
            p = selected()
            if p is None or p["manifest"] is None:
                return
            m = p["manifest"]
            existing = next((e for e in self._ext_all if e["manifest"] and e["manifest"]["id"] == m["id"]), None)
            if existing is not None and existing["scope"] != "user":
                messagebox.showinfo("Depot", "That extension ships with Blockliner and can't be replaced.", parent=win)
                return
            ok, message = depot.install(p, user_root, existing["folder"] if existing else None)
            if not ok:
                messagebox.showerror("Depot", message, parent=win)
                return
            X.set_enabled(self.settings, m["id"], False)       # never starts by itself
            self.save_app_settings()
            self._ext_all = X.find_extensions(self.extension_roots())
            self.refresh_extensions()
            messagebox.showinfo("Depot", message + "\n\nTurn it on in Tools > Extensions.", parent=win)
            refresh()

        install_button = button(bar, "Install", install)
        install_button.pack(side=tk.LEFT, padx=(0, 6))
        button(bar, "Open depot folder", lambda: self._open_folder(folder)).pack(side=tk.LEFT, padx=(0, 6))
        button(bar, "Refresh", refresh).pack(side=tk.LEFT, padx=(0, 6))
        button(bar, "Close", win.destroy).pack(side=tk.RIGHT)
        table.bind("<<TreeviewSelect>>", show_detail)
        win.bind("<Escape>", lambda _e: win.destroy())
        refresh()
        return win
