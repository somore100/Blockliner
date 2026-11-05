"""UI-builder nodes inside the app: creating them and keeping their derived
code current. The pure logic is in ui_node.py; the widget tree in ui_tree.py."""
import os
import tkinter as tk
import uuid
from tkinter import messagebox

import ui_node
import ui_pack
from nodes_model import find_node_by_id, make_node, next_order, normalize_orders  # noqa: F401
from ui_common import DARK_BG, DARK_BORDER, DARK_FG, DARK_PANEL, safe_grab_set
from ui_tree import UITree

UI_PACKS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_packs")


class UINodeMixin:

    def ui_packs_for(self, lang):
        """Every UI library (pack) for this language, default first (cached)."""
        cache = self.__dict__.setdefault("_ui_pack_cache", {})
        if lang not in cache:
            cache[lang] = ui_pack.find_packs([UI_PACKS_ROOT], lang)[0]
        return cache[lang]

    def ui_pack_for(self, lang, pack_id=None):
        """The UI pack with this id for the language, else the default one, or
        None. A UI node passes its own pack id so it keeps its own library."""
        packs = self.ui_packs_for(lang)
        for p in packs:
            if p.id == pack_id:
                return p
        return packs[0] if packs else None

    def choose_ui_pack(self, tab):
        """The UI library for a new UI node in `tab`: the one the file already
        uses, the only one there is, or the user's choice. None if cancelled."""
        packs = self.ui_packs_for(tab["language"])
        used = [ui_node.pack_id_of(n) for n, _p in self.iter_tab_nodes(tab) if ui_node.is_ui_node(n)]
        pack, ask = ui_pack.pick_pack(packs, None, used)
        if pack is None and ask:
            pack = self.ask_ui_pack(packs)
        return pack

    def ask_ui_pack(self, packs):
        """A small modal list of the UI libraries with a line about each. Returns
        the chosen pack or None."""
        win = tk.Toplevel(self)
        win.title("UI library")
        win.configure(bg=DARK_PANEL)
        win.transient(self)
        result = {"pack": None}
        choice = tk.StringVar(value=packs[0].id)
        tk.Label(win, text="Which UI library is this window for?", bg=DARK_PANEL, fg=DARK_FG,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill=tk.X, padx=16, pady=(14, 2))
        tk.Label(win, text="Later windows in this file use the same one.", bg=DARK_PANEL, fg="#888888",
                 font=("Segoe UI", 9), anchor="w").pack(fill=tk.X, padx=16, pady=(0, 8))
        for p in packs:
            row = tk.Frame(win, bg=DARK_PANEL)
            row.pack(fill=tk.X, padx=16, pady=3)
            tk.Radiobutton(row, text=p.label, variable=choice, value=p.id, bg=DARK_PANEL, fg=DARK_FG,
                           selectcolor=DARK_BG, activebackground=DARK_PANEL, activeforeground=DARK_FG,
                           font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
            if p.description:
                tk.Label(row, text=p.description, bg=DARK_PANEL, fg="#9a9a9a", font=("Segoe UI", 9), wraplength=380,
                         justify=tk.LEFT, anchor="w").pack(fill=tk.X, padx=(24, 0))

        def done(ok):
            result["pack"] = next((p for p in packs if p.id == choice.get()), None) if ok else None
            win.destroy()
        bar = tk.Frame(win, bg=DARK_PANEL)
        bar.pack(fill=tk.X, padx=16, pady=14)
        for text, ok in (("Cancel", False), ("Use this", True)):
            tk.Button(bar, text=text, command=lambda ok=ok: done(ok), bg=DARK_BG, fg=DARK_FG, relief=tk.FLAT,
                      padx=10, activebackground=DARK_BORDER, activeforeground=DARK_FG).pack(side=tk.RIGHT, padx=(6, 0))
        win.bind("<Return>", lambda e: done(True))
        win.bind("<Escape>", lambda e: done(False))
        win.protocol("WM_DELETE_WINDOW", lambda: done(False))
        safe_grab_set(win)
        self.wait_window(win)
        return result["pack"]

    def _ui_handler_resolver(self, tab):
        """target node id -> the function name an event handler is called by."""
        def resolve(target_id):
            node = find_node_by_id(tab["nodes"], target_id)
            if node is None or node.get("kind", "function") != "function":
                return None
            return ui_node.function_name(node) if ui_node.is_ui_node(node) else node["name"]
        return resolve

    def regenerate_ui_nodes(self):
        """Rewrite the derived blocks of every attached UI node in the active
        tab. Cheap, so refresh_workspace() simply does it every time; that is
        also what keeps handler names current when a function is renamed."""
        if not getattr(self, "tabs", None):
            return
        tab = self.tabs[self.active_tab_index]
        ui_nodes = [n for n, _p in self.iter_tab_nodes(tab) if ui_node.is_ui_node(n)]
        if not ui_nodes:
            return
        lang = tab["language"]
        raw_id = self.get_raw_code_block_id(lang)
        if not self.ui_packs_for(lang) or raw_id is None:
            return
        raw_param = self.get_raw_code_param_name(raw_id)
        resolve = self._ui_handler_resolver(tab)
        last = self.__dict__.setdefault("_ui_last_blocks", {})
        for node in ui_nodes:
            if ui_node.is_detached(node):
                continue
            pack = self.ui_pack_for(lang, ui_node.pack_id_of(node))
            key = (id(tab), node["id"])
            # Blocks that differ from what we generated last time were edited
            # by hand (Blocks or Code layer): keep them, detach the designer.
            if key in last and node["blocks"] and node["blocks"] != last[key]:
                ui_node.detach(node)
                continue
            if ui_node.regenerate(node, pack, raw_id, raw_param, resolve) is not None:
                last[key] = [(b, dict(p)) for b, p in node["blocks"]]

    def new_ui_node(self, tab, name, popup=False):
        """A UI node with an empty window (a popup window when `popup`), or
        None (with a message) when the tab's language has no UI pack."""
        if not self.ui_packs_for(tab["language"]):
            messagebox.showinfo("UI builder", f"There is no UI pack for {tab['language']} yet.")
            return None
        pack = self.choose_ui_pack(tab)
        if pack is None:
            return None                                  # cancelled
        root_type = next((t for t in pack.root_types if pack.widget(t).get("no_run")), pack.root_types[0]) \
            if popup else pack.root_types[0]
        tree = UITree.new(pack.id, root_type=root_type, root_name="root", props=pack.defaults(root_type),
                          is_container=pack.is_container)
        return ui_node.make_ui_node(name, str(uuid.uuid4())[:8], tree, order=next_order(tab["nodes"]))

    def reconcile_imported_ui_nodes(self, nodes, codes):
        """After a portable import: a UI node whose code is exactly what its
        tree generates stays attached (blocks re-derived); one whose code was
        edited in the file is detached so those edits are never overwritten."""
        tab = self.tabs[self.active_tab_index]
        lang = tab["language"]
        resolve = self._ui_handler_resolver({"nodes": nodes})

        def walk(level):
            for node in level:
                if ui_node.is_ui_node(node) and not ui_node.is_detached(node):
                    pack = self.ui_pack_for(lang, ui_node.pack_id_of(node))
                    if pack is None or not ui_node.matches_code(node, pack, codes.get(node["id"], ""), resolve):
                        ui_node.detach(node)
                walk(node.get("child_nodes") or [])
        walk(nodes)
