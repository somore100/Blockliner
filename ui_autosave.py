"""Ctrl+S / Ctrl+Shift+S, recovery copies of unsaved projects, and the offer to bring them back after a crash.
Rules and file handling are in autosave.py (pure). Recovery copies never replace the user's own file."""
import os
import time
import uuid
from tkinter import messagebox

import autosave
import project_file
from ui_common import APP_SETTINGS_PATH

IDLE_POLL_MS = 15000                    # how often to look again while autosave is off


class AutosaveMixin:

    def install_autosave(self):
        self._recovery_texts = {}       # recovery id -> the text last written, so nothing is rewritten for no reason
        self.bind_all("<Control-s>", self._save_key, add="+")
        self.bind_all("<Control-S>", self._save_as_key, add="+")
        self._autosave_job = self.after(self._autosave_delay(), self._autosave_tick)

    def recovery_folder(self):
        return os.path.join(os.path.dirname(APP_SETTINGS_PATH), "recovery")

    def _autosave_delay(self):
        secs = autosave.seconds(getattr(self, "settings", {}))
        return secs * 1000 if secs else IDLE_POLL_MS

    def _save_key(self, _event=None):
        self.save_project()
        return "break"

    def _save_as_key(self, _event=None):
        self.save_project_as()
        return "break"

    # ---- writing copies ------------------------------------------------------------------
    def _autosave_tick(self):
        try:
            if autosave.seconds(self.settings):
                self.autosave_now()
        except Exception as e:                      # this loop must keep running
            print(f"autosave: {e}")
        self._autosave_job = self.after(self._autosave_delay(), self._autosave_tick)

    def autosave_now(self):
        """Write a recovery copy of every project with unsaved changes that changed since the last copy.
        Returns how many were written."""
        folder = self.recovery_folder()
        self.sync_active_tab_state()
        wrote = 0
        for ws in self.workspaces:
            worth = self.workspace_dirty(ws) and not all(self._file_is_blank(f) for f in ws["files"])
            if not worth:
                self.forget_recovery(ws)            # saved or emptied since: its copy is out of date
                continue
            rid = ws.get("recovery_id")
            if not rid:
                rid = ws["recovery_id"] = uuid.uuid4().hex[:16]
            try:
                text = project_file.dumps_workspace(ws["files"], ws["active_index"], ws.get("groups"))
            except Exception:
                continue
            if self._recovery_texts.get(rid) == text:
                continue
            try:
                autosave.write_snapshot(folder, rid, text, ws["title"], ws.get("filepath"))
                self._recovery_texts[rid] = text
                wrote += 1
            except (OSError, ValueError):
                pass
        return wrote

    def forget_recovery(self, ws):
        """Delete this project's recovery copy (it was saved, or closed on purpose)."""
        rid = ws.pop("recovery_id", None)
        if rid:
            autosave.remove(self.recovery_folder(), rid)
            self._recovery_texts.pop(rid, None)

    def clear_recovery(self):
        """Leaving on purpose: nothing needs recovering."""
        autosave.clear_all(self.recovery_folder())

    # ---- bringing them back --------------------------------------------------------------
    def startup_sequence(self):
        """After the window is up: offer lost work first, then the tour (never both at once)."""
        try:
            self.offer_recovery()
        finally:
            self.maybe_start_tour()

    def offer_recovery(self):
        """Ask about projects left over from a crash. Returns how many were reopened."""
        snaps = autosave.list_snapshots(self.recovery_folder())
        if not snaps:
            return 0
        lines = "\n".join(f"  • {s['title']}   ({time.strftime('%d %b %H:%M', time.localtime(s['saved_at']))})" for s in snaps[:8])
        if len(snaps) > 8:
            lines += f"\n  … and {len(snaps) - 8} more"
        if not messagebox.askyesno(
                "Recover your work?",
                "Blockliner did not close normally last time. These projects had changes that were not saved:\n\n"
                f"{lines}\n\nOpen them again?\n(Choose No to delete these recovery copies.)"):
            self.clear_recovery()
            return 0
        pristine = [ws for ws in self.workspaces if not self.workspace_dirty(ws) and not ws.get("filepath")
                    and all(self._file_is_blank(f) for f in ws["files"])]
        opened = 0
        for snap in snaps:
            if self._reopen_snapshot(snap):
                opened += 1
        if opened:
            for ws in pristine:                     # the empty starter tab is no longer needed
                if ws in self.workspaces and len(self.workspaces) > 1:
                    self.close_workspace(self.workspaces.index(ws))
        self.clear_recovery()
        return opened

    def _reopen_snapshot(self, snap):
        try:
            files, active, notes = project_file.parse_workspace_data(
                snap["project"], self.get_available_languages(), self.current_language)
        except Exception:
            return False
        if not files:
            return False
        for i, fl in enumerate(files):
            fl["filepath"] = None
            fl["dirty"] = True                      # it is not on disk in this form
            if not fl.get("title"):
                fl["title"] = snap["title"] if len(files) == 1 else f"File {i + 1}"
        self.new_workspace(files=files, title=snap["title"], filepath=snap["filepath"], active_index=active,
                           groups=project_file.parse_workspace_groups(snap["project"]))
        self.refresh_tab_bar()
        return True
