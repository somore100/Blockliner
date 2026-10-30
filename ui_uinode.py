"""UI-builder nodes inside the app: creating them and keeping their derived
code current. The pure logic is in ui_node.py; the widget tree in ui_tree.py."""
import os
import uuid
from tkinter import messagebox

import ui_node
import ui_pack
from nodes_model import find_node_by_id, make_node, next_order, normalize_orders  # noqa: F401
from ui_tree import UITree

UI_PACKS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_packs")


class UINodeMixin:

    def ui_pack_for(self, lang):
        """The first UI pack for this language, or None (cached)."""
        cache = self.__dict__.setdefault("_ui_pack_cache", {})
        if lang not in cache:
            packs, _notes = ui_pack.find_packs([UI_PACKS_ROOT], lang)
            cache[lang] = packs[0] if packs else None
        return cache[lang]

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
        pack = self.ui_pack_for(lang)
        raw_id = self.get_raw_code_block_id(lang)
        if pack is None or raw_id is None:
            return
        raw_param = self.get_raw_code_param_name(raw_id)
        resolve = self._ui_handler_resolver(tab)
        last = self.__dict__.setdefault("_ui_last_blocks", {})
        for node in ui_nodes:
            if ui_node.is_detached(node):
                continue
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
        pack = self.ui_pack_for(tab["language"])
        if pack is None:
            messagebox.showinfo("UI builder", f"There is no UI pack for {tab['language']} yet.")
            return None
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
        pack = self.ui_pack_for(tab["language"])
        resolve = self._ui_handler_resolver({"nodes": nodes})

        def walk(level):
            for node in level:
                if ui_node.is_ui_node(node) and not ui_node.is_detached(node):
                    if pack is None or not ui_node.matches_code(node, pack, codes.get(node["id"], ""), resolve):
                        ui_node.detach(node)
                walk(node.get("child_nodes") or [])
        walk(nodes)
