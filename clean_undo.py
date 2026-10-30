"""Clean project: a short undo window. Pure module (no Tk).

"Clean project" empties the open project but keeps a copy in memory for a
while, so a mistake can be undone. The copy is dropped when the time is up.
Setting "clean_undo_seconds" (Settings > Files) sets how long; 0 turns the
undo off.
"""
import copy

DEFAULT_SECONDS = 120
MAX_SECONDS = 3600


def undo_seconds(settings):
    """The window length from settings: a whole number of seconds, 0..3600."""
    value = (settings if isinstance(settings, dict) else {}).get("clean_undo_seconds", DEFAULT_SECONDS)
    try:
        return max(0, min(MAX_SECONDS, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_SECONDS


def format_remaining(seconds):
    """1:58 for 118 seconds."""
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class UndoWindow:
    """Holds one snapshot until `seconds` have passed (time is passed in, so
    this is testable without waiting)."""

    def __init__(self):
        self._snapshot = None
        self._expires = 0.0

    def start(self, snapshot, seconds, now):
        """Keep a deep copy of `snapshot`; False when seconds is 0 (no undo)."""
        self.drop()
        if seconds <= 0:
            return False
        self._snapshot = copy.deepcopy(snapshot)
        self._expires = now + seconds
        return True

    def remaining(self, now):
        if self._snapshot is None:
            return 0.0
        left = self._expires - now
        if left <= 0:
            self.drop()
            return 0.0
        return left

    def active(self, now):
        return self.remaining(now) > 0

    def take(self, now):
        """The snapshot, once; None when none is kept or the time is up."""
        if not self.active(now):
            return None
        snapshot, self._snapshot = self._snapshot, None
        return snapshot

    def drop(self):
        self._snapshot = None
        self._expires = 0.0
