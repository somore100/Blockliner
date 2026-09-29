"""Panel manager for the Blockliner main window.

Every major area of the window (block palette, workspace, generated
code, and later plugin panels) is a *panel*: it is registered with a
PanelSpec and gets back a plain tk.Frame to build its contents into.
The manager owns where those frames live, using one horizontal
tk.PanedWindow, so panels are resizable via sashes and can be
shown / hidden by id without the rest of the app knowing how the
layout works.

Deliberately small. It does NOT do drag/drop docking, collapse strips,
right-click menus or layout persistence yet - those get built on top of
this API (see the listener hook and get_state/apply_state below).

Usage:
    panels = PanelManager(parent, bg="#1e1e1e")
    panels.paned.pack(fill=tk.BOTH, expand=True)
    left = panels.create_panel(PanelSpec("palette", "Blocks", dock="left"))
    ...build widgets into `left`...
    panels.hide("palette")
    panels.show("palette")
"""

import tkinter as tk
from dataclasses import dataclass

# Left-to-right order of the docks. Within one dock, panels keep
# registration order.
DOCK_ORDER = {"left": 0, "center": 1, "right": 2}


@dataclass
class PanelSpec:
    id: str                    # unique key, e.g. "palette"
    title: str                 # human name (menus, collapse strips later)
    dock: str = "center"       # "left" | "center" | "right"
    width: int = 300           # default width in pixels
    min_width: int = 120       # a sash can't squeeze the panel below this
    stretch: bool = False      # True: takes the leftover space on window resize


class PanelManager:
    def __init__(self, parent, bg, sash_width=6):
        # sash_width=6 with a flat sash in the window background colour
        # reproduces the old 3px+3px padding gap between panels, while
        # making the gap draggable.
        self.paned = tk.PanedWindow(
            parent,
            orient=tk.HORIZONTAL,
            bg=bg,
            bd=0,
            sashwidth=sash_width,
            sashrelief=tk.FLAT,
            showhandle=False,
            opaqueresize=True,
        )
        self._specs = {}       # id -> PanelSpec (registration order)
        self._frames = {}      # id -> tk.Frame
        self._visible = {}     # id -> bool
        self._widths = {}      # id -> last known width in px
        self._listeners = []   # callables (panel_id, visible)

    # ------------------------------------------------------------ setup

    def create_panel(self, spec, bg=None, visible=True):
        """Register a panel and return its (empty) content frame."""
        if spec.id in self._specs:
            raise ValueError(f"panel id already registered: {spec.id!r}")
        if spec.dock not in DOCK_ORDER:
            raise ValueError(f"unknown dock {spec.dock!r}; use one of {sorted(DOCK_ORDER)}")

        frame = tk.Frame(self.paned, width=spec.width)
        if bg is not None:
            frame.configure(bg=bg)
        # Size comes from the spec, not from whatever gets packed inside.
        frame.pack_propagate(False)

        self._specs[spec.id] = spec
        self._frames[spec.id] = frame
        self._visible[spec.id] = False
        self._widths[spec.id] = spec.width
        if visible:
            self.show(spec.id)
        return frame

    # ------------------------------------------------------------ queries

    def ids(self):
        """Panel ids in on-screen order (dock order, then registration)."""
        return self._sorted_ids()

    def spec(self, panel_id):
        return self._specs[panel_id]

    def frame(self, panel_id):
        return self._frames[panel_id]

    def is_visible(self, panel_id):
        self._require(panel_id)
        return self._visible[panel_id]

    def width(self, panel_id):
        """Current width if shown, else the width it will reopen at."""
        self._require(panel_id)
        if self._visible[panel_id]:
            w = self._frames[panel_id].winfo_width()
            if w > 1:
                return w
        return self._widths[panel_id]

    # ------------------------------------------------------------ actions

    def show(self, panel_id):
        self._require(panel_id)
        if self._visible[panel_id]:
            return
        spec = self._specs[panel_id]
        frame = self._frames[panel_id]
        opts = dict(
            minsize=spec.min_width,
            stretch="always" if spec.stretch else "never",
            width=max(self._widths[panel_id], spec.min_width),
        )
        # Re-insert at the right spot: before the next visible panel
        # that comes after this one in dock order.
        order = self._sorted_ids()
        after = order[order.index(panel_id) + 1:]
        nxt = next((i for i in after if self._visible[i]), None)
        if nxt is not None:
            self.paned.add(frame, before=self._frames[nxt], **opts)
        else:
            self.paned.add(frame, **opts)
        self._visible[panel_id] = True
        self._notify(panel_id, True)

    def hide(self, panel_id):
        self._require(panel_id)
        if not self._visible[panel_id]:
            return
        frame = self._frames[panel_id]
        w = frame.winfo_width()
        if w > 1:                      # remember the width it had
            self._widths[panel_id] = w
        self.paned.forget(frame)
        self._visible[panel_id] = False
        self._notify(panel_id, False)

    def set_visible(self, panel_id, visible):
        (self.show if visible else self.hide)(panel_id)

    def toggle(self, panel_id):
        self.set_visible(panel_id, not self.is_visible(panel_id))

    def set_width(self, panel_id, px):
        """Resize a panel. Works while shown (moves the sash) and while
        hidden (sets the width it will reopen at)."""
        self._require(panel_id)
        px = max(int(px), self._specs[panel_id].min_width)
        self._widths[panel_id] = px
        if self._visible[panel_id]:
            self.paned.paneconfigure(self._frames[panel_id], width=px)

    # ------------------------------------------------------------ hooks

    def add_listener(self, fn):
        """fn(panel_id, visible) is called after every show/hide. This is
        what collapse strips and right-click menus will hang off."""
        self._listeners.append(fn)

    def get_state(self):
        """Plain-dict snapshot (visibility + widths) for saving later."""
        return {i: {"visible": self._visible[i], "width": self.width(i)}
                for i in self._specs}

    def apply_state(self, state):
        """Restore a get_state() snapshot. Unknown ids are ignored so an
        old layout never breaks when a plugin panel is gone."""
        for pid, s in state.items():
            if pid not in self._specs:
                continue
            self.set_width(pid, s.get("width", self._widths[pid]))
            self.set_visible(pid, bool(s.get("visible", True)))

    # ------------------------------------------------------------ internals

    def _sorted_ids(self):
        seq = {pid: n for n, pid in enumerate(self._specs)}
        return sorted(self._specs, key=lambda i: (DOCK_ORDER[self._specs[i].dock], seq[i]))

    def _require(self, panel_id):
        if panel_id not in self._specs:
            raise KeyError(f"unknown panel id: {panel_id!r}")

    def _notify(self, panel_id, visible):
        for fn in list(self._listeners):
            fn(panel_id, visible)
