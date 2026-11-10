"""Project-wide undo in the app: File > Undo / Redo, Ctrl+Z / Ctrl+Y, and the
small bar that follows a change ("Hello changed the project: ... [Undo]").
The rules are pure (project_undo.py). Snapshots are recorded before an
extension's edit and before code typed in the panel is turned into blocks, so
Ctrl+Z in the code panel steps back over the last such change."""
import tkinter as tk

import project_undo
from ui_common import DARK_ACCENT, DARK_BORDER, DARK_FG, DARK_PANEL

BAR_SECONDS = 12
TEXT_CLASSES = ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Text")


class ProjectUndoMixin:

    def install_project_undo(self):
        self._change_bar = None
        self._change_job = None
        self.bind_all("<Control-z>", self._undo_key, add="+")
        self.bind_all("<Control-y>", self._redo_key, add="+")
        self.bind_all("<Control-Z>", self._redo_key, add="+")
        # the code panel is a Text: its own binding wins over the generic one
        self.code_text.bind("<Control-z>", lambda _e: (self.undo_project(), "break")[1])
        self.code_text.bind("<Control-y>", lambda _e: (self.undo_project(redo=True), "break")[1])

    def _undo_stack(self):
        ws = self.workspaces[self.active_ws_index]
        # kept on the workspace itself, so a closed project takes its history along
        return ws.setdefault("undo_stack", project_undo.UndoStack())

    def _typing_in_a_box(self):
        w = self.focus_get()
        return w is not None and w.winfo_class() in TEXT_CLASSES and w is not self.code_text

    def _undo_key(self, _event):
        if self._typing_in_a_box():
            return None
        self.undo_project()
        return "break"

    def _redo_key(self, _event):
        if self._typing_in_a_box():
            return None
        self.undo_project(redo=True)
        return "break"

    def record_project_undo(self, label):
        """Remember how the project looks BEFORE a change that should be undoable."""
        self.sync_active_tab_state()
        ws = self.workspaces[self.active_ws_index]
        self._undo_stack().record(label, project_undo.files_state(ws["files"], ws["active_index"]))

    def undo_project(self, redo=False):
        self.sync_active_tab_state()
        ws = self.workspaces[self.active_ws_index]
        stack = self._undo_stack()
        current = project_undo.files_state(ws["files"], ws["active_index"])
        step = stack.redo(current) if redo else stack.undo(current)
        if step is None:
            self.bell()
            return False
        label, state = step
        self.restore_project_state(state)
        self.show_change_bar(f"{'Redid' if redo else 'Undid'}: {label}", undo=False)
        return True

    def restore_project_state(self, state):
        """Swap a snapshot back in and refresh everything that shows the project."""
        if self.multi_active():
            self.multi_exit()
        ws = self.workspaces[self.active_ws_index]
        ws["active_index"] = project_undo.restore_files(ws["files"], state)
        self._show_active_file(self.view_mode)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        self.update_generated_code()

    def show_change_bar(self, text, undo=True):
        """A small bar at the bottom for a few seconds: what changed, with Undo."""
        self.hide_change_bar()
        bar = tk.Frame(self, bg=DARK_PANEL, highlightthickness=1, highlightbackground=DARK_BORDER)
        tk.Label(bar, text=text[:140], bg=DARK_PANEL, fg=DARK_FG, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(10, 8), pady=6)
        if undo and self._undo_stack().can_undo():
            tk.Button(bar, text="Undo", bg=DARK_ACCENT, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
                      font=("Segoe UI", 9, "bold"), command=lambda: (self.hide_change_bar(), self.undo_project())).pack(side=tk.LEFT, padx=(0, 4), pady=4)
        tk.Button(bar, text="✕", bg=DARK_PANEL, fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                  command=self.hide_change_bar).pack(side=tk.LEFT, padx=(0, 6))
        bar.place(relx=0.5, rely=1.0, y=-14, anchor="s")
        self._change_bar = bar
        self._change_job = self.after(BAR_SECONDS * 1000, self.hide_change_bar)

    def hide_change_bar(self):
        if self._change_job is not None:
            try:
                self.after_cancel(self._change_job)
            except tk.TclError:
                pass
            self._change_job = None
        if self._change_bar is not None:
            self._change_bar.destroy()
            self._change_bar = None
