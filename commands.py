"""Commands: everything the app can do, by id (pure, no Tk).

Menus, the command palette and extensions all work from one registry, so a
thing that can be done is described once: an id, a title, where it sits in the
menus, and what it runs. Extensions add commands under their own owner id and
take them away again with unregister_owner.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import palette_search

MENU_ORDER = ("File", "Run", "Tools", "Help")


@dataclass
class Command:
    id: str
    title: str
    run: Callable
    menu: Optional[str] = None        # menu it appears in; None = palette only
    group: int = 0                    # entries of one group sit together, a separator between groups
    keywords: str = ""                # extra words the palette search matches
    shortcut: str = ""                # shown in the palette, e.g. "Ctrl+Z"
    owner: Optional[str] = None       # None for the app, else the extension id
    enabled: Optional[Callable] = None

    def is_enabled(self):
        return self.enabled is None or bool(self.enabled())

    def where(self):
        """'File > Save' style place, for the palette."""
        return f"{self.menu} › {self.title}" if self.menu else self.title


class CommandRegistry:
    def __init__(self):
        self._commands = []           # registration order is the menu order

    def register(self, command):
        if any(c.id == command.id for c in self._commands):
            raise ValueError(f"command '{command.id}' is already registered")
        self._commands.append(command)
        return command

    def unregister_owner(self, owner):
        """Remove every command of one owner (an extension that was turned off)."""
        self._commands = [c for c in self._commands if c.owner != owner]

    def get(self, command_id):
        return next((c for c in self._commands if c.id == command_id), None)

    def all(self):
        return list(self._commands)

    def run(self, command_id):
        """Run a command; False when it is unknown or currently disabled."""
        command = self.get(command_id)
        if command is None or not command.is_enabled():
            return False
        command.run()
        return True

    def menu_entries(self, menu):
        """[(title, run) | None] for one menu: app commands first by group, then
        a separator and the extensions' commands. None is a separator."""
        entries = [c for c in self._commands if c.menu == menu]
        out = []
        for owner_is_app in (True, False):
            part = [c for c in entries if (c.owner is None) == owner_is_app]
            part.sort(key=lambda c: c.group)          # stable: keeps registration order inside a group
            if out and part:
                out.append(None)
            last = None
            for c in part:
                if last is not None and c.group != last:
                    out.append(None)
                out.append((c.title, c.run))
                last = c.group
        return out

    def menus(self):
        """Menu titles in display order: the standard ones, then any others commands name."""
        named = {c.menu for c in self._commands if c.menu}
        return list(MENU_ORDER) + sorted(named - set(MENU_ORDER))

    def search(self, query, limit=30):
        """Enabled commands matching `query`, best first (all of them, in menu
        order, for an empty query)."""
        scored = []
        for index, c in enumerate(self._commands):
            if not c.is_enabled():
                continue
            s = palette_search.score(query, {"name": c.title, "keywords": c.keywords,
                                             "category": c.menu or "", "id": c.id.replace(".", " ").replace(":", " ")})
            if s > 0:
                scored.append((-s, index, c))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [c for _s, _i, c in scored[:limit]]
