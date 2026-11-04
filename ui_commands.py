"""The app's commands and the command palette (Ctrl+Shift+P).

The commands themselves are described once, here, in CORE; menus are built
from the registry (commands.py), and extensions add their own commands to it.
Handlers are looked up by name when a command runs, so replacing a method
(or an extension reloading) always reaches the current one.
"""
import tkinter as tk

from commands import Command, CommandRegistry
from ui_common import DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL

STANDARD_MENUS = ("File", "Run", "Tools", "Help")

# (id, title, menu, group, handler(app), shortcut, extra search words)
CORE = [
    ("file.undo", "Undo", "File", 0, lambda a: a.undo_project(), "Ctrl+Z", "step back revert"),
    ("file.redo", "Redo", "File", 0, lambda a: a.undo_project(redo=True), "Ctrl+Y", "step forward"),
    ("file.save", "Save", "File", 1, lambda a: a.save_project(), "", "write store project"),
    ("file.load", "Load", "File", 1, lambda a: a.load_project(), "", "open project"),
    ("file.open_project", "Open Project...", "File", 1, lambda a: a.open_project_dialog(), "", "folder"),
    ("file.open_code", "Open Code File...", "File", 1,
     lambda a: a.open_code_to_blocks_dialog(prefill_from_file=True), "", "import source"),
    ("file.paste_code", "Paste Code as Nodes...", "File", 1, lambda a: a.open_code_to_blocks_dialog(), "", "import text"),
    ("file.export", "Export", "File", 1, lambda a: a.export_code(), "", "save code file"),
    ("file.clean", "Clean Project...", "File", 2, lambda a: a.clean_project(), "", "tidy remove unused"),
    ("run.run", "Run in Blockliner", "Run", 0, lambda a: a.run_code(), "", "execute start"),
    ("run.terminal", "Run in Terminal", "Run", 0, lambda a: a.run_in_terminal(), "", "execute shell"),
    ("run.vscode", "Open in VS Code", "Run", 0, lambda a: a.open_in_vscode(), "", "editor"),
    ("run.export_run", "Export & Run...", "Run", 1, lambda a: a.export_and_run(), "", "execute file"),
    ("run.clear", "Clear", "Run", 2, lambda a: a.clear_all(), "", "empty reset"),
    ("tools.custom_blocks", "Manage Custom Blocks...", "Tools", 0, lambda a: a.manage_custom_blocks_dialog(), "", "make blocks"),
    ("tools.imports", "Imports...", "Tools", 0, lambda a: a.show_import_manager(), "", "libraries modules"),
    ("tools.extensions", "Extensions...", "Tools", 0, lambda a: a.show_extension_manager(), "", "plugins addons"),
    ("tools.ai", "AI tools connection...", "Tools", 0, lambda a: a.show_control_dialog(), "", "agent mcp claude"),
    ("tools.settings", "Settings", "Tools", 0, lambda a: a.settings_dialog(), "", "options preferences"),
    ("tools.palette", "Command palette...", "Tools", 1, lambda a: a.show_command_palette(), "Ctrl+Shift+P", "find run action search"),
    ("tools.depot", "Extension depot...", None, 0, lambda a: a.show_depot(), "", "install update packages extensions"),
    ("help.feedback", "Leave Feedback...", "Help", 0, lambda a: a.show_feedback(), "", "report bug idea"),
    ("help.about", "About Blockliner", "Help", 0, lambda a: a.show_about(), "", "version license"),
]


class CommandsMixin:

    @property
    def command_registry(self):
        reg = self.__dict__.get("_command_registry")
        if reg is None:
            reg = self.__dict__["_command_registry"] = CommandRegistry()
            for cid, title, menu, group, call, shortcut, words in CORE:
                reg.register(Command(cid, title, lambda c=call: c(self), menu, group, words, shortcut))
        return reg

    def install_commands(self):
        for seq in ("<Control-Shift-P>", "<Control-Shift-p>"):
            self.bind_all(seq, lambda _e: (self.show_command_palette(), "break")[1])

    # ---- menus ------------------------------------------------------------------
    def topbar_menu_spec(self):
        """[(title, [(label, command) | None for a separator])], from the registry."""
        return [(title, self.command_registry.menu_entries(title)) for title in STANDARD_MENUS]

    def refresh_topbar_menus(self):
        """Redraw the menus after commands were added or removed (an extension turned on or off)."""
        subs = getattr(self, "_burger_subs", {})
        for title, entries in self.topbar_menu_spec():
            for menu in (self.topbar_menus.get(title), subs.get(title)):
                if menu is not None:
                    menu.delete(0, "end")
                    self._fill_menu(menu, entries)

    # ---- extensions' commands -------------------------------------------------------
    def sync_extension_commands(self):
        """Put the active extensions' commands (and a 'Show <panel>' for each panel) in the registry."""
        reg = self.command_registry
        for ext in getattr(self, "_ext_all", []):
            reg.unregister_owner(ext["manifest"]["id"])
        layout = getattr(self, "_ext_layout", None) or {"commands": [], "pinned": [], "overflow_panels": []}

        def add(ext, cid, title, menu, run):
            try:
                reg.register(Command(f"ext:{ext['manifest']['id']}:{cid}", title, run, menu, 0, owner=ext["manifest"]["id"]))
            except ValueError:
                pass
        for ext, command in layout["commands"]:
            menu = command["menu"] if command.get("menu") in STANDARD_MENUS else None
            add(ext, command["command"], command["label"], menu, lambda e=ext, c=command["command"]: self.extension_command(e, c))
        for ext in layout["pinned"] + layout["overflow_panels"]:
            add(ext, "panel", f"Show {ext['manifest']['panel']['title']} panel", None, lambda e=ext: self.toggle_extension_panel(e))
        self.refresh_topbar_menus()

    # ---- the palette ----------------------------------------------------------------
    def show_command_palette(self):
        existing = getattr(self, "_palette_win", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        win = tk.Toplevel(self)
        self._palette_win = win
        win.title("Command palette")
        win.configure(bg=DARK_PANEL)
        win.transient(self)
        width, height = 560, 380
        try:
            x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + 70
        except tk.TclError:
            x, y = 200, 120
        win.geometry(f"{width}x{height}+{x}+{y}")
        query = tk.StringVar()
        entry = tk.Entry(win, textvariable=query, bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_FG, relief=tk.FLAT,
                         font=("Segoe UI", 12))
        entry.pack(fill=tk.X, padx=12, pady=(12, 6), ipady=6)
        box = tk.Listbox(win, bg=DARK_BG, fg=DARK_FG, selectbackground=DARK_ACCENT, selectforeground="#ffffff",
                         highlightthickness=0, relief=tk.FLAT, activestyle="none", font=("Segoe UI", 10))
        box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        shown = []

        def refill(*_):
            shown[:] = self.command_registry.search(query.get())
            box.delete(0, tk.END)
            for c in shown:
                box.insert(tk.END, c.where() + (f"      {c.shortcut}" if c.shortcut else ""))
            if shown:
                box.selection_set(0)

        def move(delta):
            if not shown:
                return "break"
            cur = box.curselection()
            i = max(0, min(len(shown) - 1, (cur[0] if cur else 0) + delta))
            box.selection_clear(0, tk.END)
            box.selection_set(i)
            box.see(i)
            return "break"

        def run(_e=None):
            cur = box.curselection()
            if not shown or not cur:
                return "break"
            command = shown[cur[0]]
            win.destroy()
            self.after(30, command.run)            # after the palette is gone, so dialogs get focus
            return "break"

        query.trace_add("write", refill)
        entry.bind("<Down>", lambda _e: move(1))
        entry.bind("<Up>", lambda _e: move(-1))
        entry.bind("<Return>", run)
        box.bind("<Double-Button-1>", run)
        win.bind("<Escape>", lambda _e: win.destroy())
        refill()
        entry.focus_set()
        return win
