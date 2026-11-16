"""File > Follow a folder (read-only): source-first mode, phase 1 (docs/source-first-mode.md).

The files in the folder are the truth. Every source file becomes a file tab with nodes made from its structure; a timer
looks at the folder every couple of seconds, and when an outside tool (an editor, an AI agent) adds or changes a file the
layers update by themselves, keeping the nodes where they were. Nothing is ever written to the folder: edits made in
Blockliner stay in Blockliner and are replaced the next time the file changes on disk."""
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import portable
import project_scan
import source_follow
from ui_common import LANGUAGE_EXTENSIONS

FOLLOW_MS = 1500


class FollowMixin:
    _follow = None             # {"folder", "snap": {rel: info}, "job"} while a folder is followed

    def follow_folder(self, folder=None):
        """Pick a folder and start following it. Returns how many files were opened (0 = nothing started)."""
        if self._follow is not None:
            self.stop_following()
        if folder is None:
            folder = filedialog.askdirectory(title="Follow a folder - pick the project's root folder")
        if not folder:
            return 0
        snap = source_follow.snapshot(folder, LANGUAGE_EXTENSIONS)
        if not snap:
            messagebox.showinfo("Follow a folder", "There are no source files Blockliner can read in that folder.")
            return 0
        self._follow = {"folder": os.path.abspath(folder), "snap": {}, "job": None}
        opened = 0
        for rel in sorted(snap):
            if self._follow_open_file(rel, snap[rel]):
                opened += 1
        self._follow["snap"] = snap
        if opened:
            self.goto_layer("files")
        self._follow_schedule()
        messagebox.showinfo(
            "Following a folder",
            f"Following {os.path.basename(self._follow['folder']) or folder}: {opened} file(s).\n\n"
            "The files on disk are the truth. When another program changes a file, Blockliner updates by itself.\n"
            "This mode is read-only for now: Blockliner never writes to these files, and what you change here is "
            "replaced the next time the file changes on disk.")
        return opened

    def stop_following(self):
        f, self._follow = self._follow, None
        if f and f.get("job") is not None:
            try:
                self.after_cancel(f["job"])
            except tk.TclError:
                pass
        for tab in getattr(self, "tabs", []):
            tab.pop("followed", None)

    # ---- the watcher ----------------------------------------------------
    def _follow_schedule(self, took=0.0):
        """Next look in FOLLOW_MS, or later when the last look was slow (a big folder): never more than ~10% busy."""
        if self._follow is not None:
            self._follow["job"] = self.after(max(FOLLOW_MS, int(took * 10000)), self._follow_tick)

    def _follow_tick(self):
        f = self._follow
        if f is None:
            return
        t0 = time.time()
        try:
            self.follow_check_now()
        except Exception as exc:                    # a watcher must never take the window down
            print(f"follow: {exc}")
        self._follow_schedule(time.time() - t0)

    def follow_check_now(self):
        """One look at the folder. Returns (added, changed, removed) relative paths."""
        f = self._follow
        if f is None:
            return [], [], []
        new = source_follow.snapshot(f["folder"], LANGUAGE_EXTENSIONS, previous=f["snap"])
        added, changed, removed = source_follow.diff(f["snap"], new)
        if not (added or changed or removed):
            f["snap"] = new
            return added, changed, removed
        back = self.active_tab_index
        keep = self.tabs[back] if 0 <= back < len(self.tabs) else None
        for rel in added:
            self._follow_open_file(rel, new[rel])
        for rel in changed:
            tab = self._follow_tab(rel)
            if tab is None:
                self._follow_open_file(rel, new[rel])
            else:
                self._follow_reload(tab, rel, new[rel])
        for rel in removed:
            tab = self._follow_tab(rel)
            if tab is not None and not tab.get("title", "").endswith(" (missing)"):
                tab["title"] += " (missing)"
        f["snap"] = new
        if keep in self.tabs and self.tabs.index(keep) != self.active_tab_index:
            self.switch_to_tab(self.tabs.index(keep))
        self.refresh_tab_bar()
        return added, changed, removed

    # ---- one file ---------------------------------------------------------
    def _follow_tab(self, rel):
        for tab in self.tabs:
            if tab.get("followed") == rel:
                return tab
        return None

    def _follow_entry(self, rel, info):
        return {"rel": rel, "path": info["path"], "language": info["language"], "ok": True}

    def _follow_open_file(self, rel, info):
        """Open one file of the folder as a new tab, marked as followed. True when it opened."""
        before = len(self.tabs)
        if self.import_project_file(self._follow_entry(rel, info), True) is None or len(self.tabs) == before:
            return False
        tab = self.tabs[-1]
        tab["followed"] = rel
        tab["dirty"] = False                         # it is on disk exactly like this
        return True

    def _follow_reload(self, tab, rel, info):
        """Read the file again into an existing tab, keeping the nodes where they were."""
        try:
            text = project_scan.read_text(info["path"])
        except OSError:
            return False
        lang = info["language"]
        token = self.get_comment_token(lang) or "#"
        chunks = portable.split_top_level(text)
        if not chunks:
            stem = os.path.splitext(os.path.basename(rel))[0]
            chunks = [(stem or "main", text)]
        marked = portable.wrap_with_markers(chunks, token)
        idx = self.tabs.index(tab)
        if idx != self.active_tab_index:
            self.switch_to_tab(idx)                  # the block matcher works on the current language
        nodes, active, _diag = self.nodes_from_portable_text(marked, lang)
        if not nodes:
            return False
        source_follow.carry_layout(tab["nodes"], nodes)
        tab["nodes"], tab["active_node_id"], tab["dirty"] = nodes, active, False
        tab["title"] = project_scan.node_title(rel)
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.refresh_workspace()
        return True
