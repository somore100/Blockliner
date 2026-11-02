"""Project-wide undo (pure, no Tk): whole-project snapshots, not per-keystroke.

The app records a snapshot before a change that should be undoable (an
extension's edit, a code-to-blocks sync). Undo swaps the project back to the
last snapshot and keeps the state it replaced for redo. Snapshots are deep
copies, so they never change afterwards. `limit` keeps memory in check.
"""
import copy

DEFAULT_LIMIT = 20


class UndoStack:

    def __init__(self, limit=DEFAULT_LIMIT):
        self.limit = limit
        self._undo, self._redo = [], []          # [(label, state)]

    def record(self, label, state):
        """Remember `state` (what the project looks like BEFORE the change)."""
        self._undo.append((label, copy.deepcopy(state)))
        del self._undo[:-self.limit]
        self._redo.clear()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo_label(self):
        return self._undo[-1][0] if self._undo else ""

    def redo_label(self):
        return self._redo[-1][0] if self._redo else ""

    def undo(self, current_state):
        """(label, state to restore) or None; `current_state` is kept for redo."""
        if not self._undo:
            return None
        label, state = self._undo.pop()
        self._redo.append((label, copy.deepcopy(current_state)))
        return label, state

    def redo(self, current_state):
        if not self._redo:
            return None
        label, state = self._redo.pop()
        self._undo.append((label, copy.deepcopy(current_state)))
        return label, state

    def clear(self):
        self._undo.clear()
        self._redo.clear()


def files_state(files, active_index):
    """A snapshot of a workspace's files."""
    return {"files": copy.deepcopy(files), "active_index": active_index}


def restore_files(files, state):
    """Put a snapshot back into the live `files` list (in place) and return its
    active index. The snapshot stays usable (it is copied again)."""
    files[:] = copy.deepcopy(state["files"])
    return state["active_index"] if 0 <= state["active_index"] < len(files) else 0
