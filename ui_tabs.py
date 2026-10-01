"""Tabs/files, app settings and per-language setup."""
import tkinter as tk
from tkinter import messagebox
import os
import json
import uuid
from nodes_model import default_active_node_id, find_node_by_id, make_node
from ui_common import APP_SETTINGS_PATH, DARK_ACCENT, DARK_BORDER, DARK_FG, DARK_PANEL, DEFAULT_SETTINGS, get_block_attr


class TabsMixin:
    
    def get_active_node(self, tab=None):
        """Return the currently-active node dict for `tab` (defaulting
        to the active tab), searching into class nodes' child_nodes at
        any depth since B3's auto-created entry point can be nested
        inside an auto-created wrapping class. Falls back to the first
        function-kind node found anywhere (never a class node itself -
        it has no blocks to edit), and - purely as a defensive last
        resort for a tab that somehow has no nodes at all - creates a
        fresh "main" node rather than raising, since losing the
        workspace entirely on a lookup miss would be a far worse
        failure than silently recovering an empty one."""
        tab = tab if tab is not None else self.tabs[self.active_tab_index]
        if not tab.get("nodes"):
            tab["nodes"] = [make_node("main", node_id="main")]
            tab["active_node_id"] = tab["nodes"][0]["id"]

        found = find_node_by_id(tab["nodes"], tab.get("active_node_id"))
        if found is not None and found.get("kind", "function") == "function":
            return found

        fallback_id = default_active_node_id(tab["nodes"])
        fallback = find_node_by_id(tab["nodes"], fallback_id) if fallback_id else None
        return fallback or tab["nodes"][0]

    def set_project_blocks(self, new_list):
        """
        Reassign self.project_blocks to an entirely new list (as opposed
        to mutating the existing one in place, e.g. .append()/.pop()).
        Always goes through here so the active tab's active node's own
        stored reference gets updated too - otherwise the node would
        silently keep pointing at the old (now stale) list after a full
        reload like Code -> Blocks or Load Project.
        """
        self.project_blocks = new_list
        if getattr(self, "tabs", None):
            self.get_active_node()["blocks"] = new_list

    def sync_active_tab_state(self):
        """Write the currently-active tab's live language/project_blocks
        back into its stored slot. project_blocks is normally already
        the same list object (mutations like .append()/.pop() keep it
        in sync automatically), but this also covers current_language,
        and is cheap insurance before switching away from a tab."""
        if not getattr(self, "tabs", None):
            return
        tab = self.tabs[self.active_tab_index]
        tab["language"] = self.current_language
        self.get_active_node(tab)["blocks"] = self.project_blocks

    def mark_active_tab_dirty(self):
        if getattr(self, "tabs", None):
            self.tabs[self.active_tab_index]["dirty"] = True
            self.refresh_tab_bar()

    def switch_to_tab(self, index):
        if not (0 <= index < len(self.tabs)) or index == self.active_tab_index:
            return
        self.sync_active_tab_state()

        self.active_tab_index = index
        tab = self.tabs[index]
        self.current_language = tab["language"]
        self.project_blocks = self.get_active_node(tab)["blocks"]
        self.view_mode = "node"

        self.lang_var.set(self.current_language)
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()
        self.refresh_palette()
        self.refresh_workspace()
        self.refresh_tab_bar()

    def _append_new_tab(self):
        """Add a fresh Untitled tab WITHOUT switching to it; returns it."""
        self.sync_active_tab_state()
        title = f"Untitled {self._next_untitled_number}"
        self._next_untitled_number += 1
        new_nodes = self.build_initial_nodes_for_language(self.current_language)
        tab = {
            "title": title,
            "language": self.current_language,
            "nodes": new_nodes,
            "active_node_id": default_active_node_id(new_nodes),
            "filepath": None,
            "dirty": False,
        }
        self.tabs.append(tab)
        return tab

    def new_tab(self):
        self._append_new_tab()
        self.switch_to_tab(len(self.tabs) - 1)

    def create_file_at(self, pos):
        """Files-layer right-click 'New file': add a tab as a box at the
        cursor and stay on the Files layer (new_tab() would switch away)."""
        tab = self._append_new_tab()
        tab["canvas_x"], tab["canvas_y"] = pos
        self.refresh_tab_bar()
        self.refresh_workspace()

    def close_tab(self, index):
        if not (0 <= index < len(self.tabs)):
            return
        tab = self.tabs[index]

        if tab["dirty"]:
            proceed = messagebox.askyesno(
                "Unsaved Changes",
                f"'{tab['title']}' has unsaved changes. Close it anyway?"
            )
            if not proceed:
                return

        self.tabs.pop(index)

        if not self.tabs:
            # Always keep at least one tab open.
            fallback_nodes = self.build_initial_nodes_for_language(self.current_language)
            self.tabs.append({
                "title": f"Untitled {self._next_untitled_number}",
                "language": self.current_language,
                "nodes": fallback_nodes,
                "active_node_id": default_active_node_id(fallback_nodes),
                "filepath": None,
                "dirty": False,
            })
            self._next_untitled_number += 1

        if index < self.active_tab_index:
            self.active_tab_index -= 1
        elif index == self.active_tab_index:
            self.active_tab_index = min(self.active_tab_index, len(self.tabs) - 1)
            tab = self.tabs[self.active_tab_index]
            self.current_language = tab["language"]
            self.project_blocks = self.get_active_node(tab)["blocks"]
            self.view_mode = "node"
            self.lang_var.set(self.current_language)
            self.load_blocks_for_language(self.current_language)
            self.load_and_merge_custom_blocks()
            self.refresh_palette()
            self.refresh_workspace()

        self.refresh_tab_bar()

    def refresh_tab_bar(self):
        """Redraw the tab strip at the top of the window."""
        for widget in self.tab_bar_frame.winfo_children():
            if widget is getattr(self, "layer_bar", None):
                continue
            widget.destroy()

        for i, tab in enumerate(self.tabs):
            is_active = (i == self.active_tab_index)
            tab_frame = tk.Frame(
                self.tab_bar_frame,
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                highlightthickness=1,
                highlightbackground=DARK_BORDER
            )
            tab_frame.pack(side=tk.LEFT, padx=(0, 2), pady=2)

            label_text = tab["title"] + (" \u25CF" if tab["dirty"] else "")
            label = tk.Label(
                tab_frame, text=label_text,
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                fg=("#ffffff" if is_active else DARK_FG),
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                cursor="hand2", padx=10, pady=6
            )
            label.pack(side=tk.LEFT)
            label.bind("<Button-1>", lambda e, idx=i: self.switch_to_tab(idx))

            close_btn = tk.Label(
                tab_frame, text="\u2715",
                bg=(DARK_ACCENT if is_active else DARK_PANEL),
                fg=("#ffffff" if is_active else "#888888"),
                font=("Segoe UI", 8), cursor="hand2", padx=8
            )
            close_btn.pack(side=tk.LEFT)
            close_btn.bind("<Button-1>", lambda e, idx=i: self.close_tab(idx))

        tk.Button(
            self.tab_bar_frame, text="+", bg=DARK_PANEL, fg=DARK_FG,
            relief=tk.FLAT, font=("Segoe UI", 11, "bold"), cursor="hand2",
            width=2, command=self.new_tab
        ).pack(side=tk.LEFT, padx=(6, 0), pady=2)

        self.refresh_layer_bar()

    def load_blocks_for_language(self, lang, verbose=True):
        """
        Load blocks for a language from its JSON language pack
        (languages/<lang>/manifest.json + languages/<lang>/blocks/*.json,
        one file per block), via the V2 engine.
        """
        from engine.loader import load_language_pack
        from engine.renderer import with_generate_code

        manifest, blocks = load_language_pack(os.path.join(self.languages_path, lang), verbose=verbose)
        self.blocks = with_generate_code(blocks) if blocks else {}
        self.node_types = manifest.get("node_types", []) if manifest else []

        # Group blocks by category
        self.blocks_by_category = {}
        for block_id, block_def in self.blocks.items():
            category = get_block_attr(block_def, "category", "Basic")
            self.blocks_by_category.setdefault(category, []).append(block_def)

    def get_node_types_for_language(self, lang):
        """Fetch node_types.json for `lang` directly from disk, rather
        than relying on self.node_types (which reflects whichever
        language is CURRENTLY active) - this needs to work for the
        language a brand-new tab is ABOUT to use, including at
        __init__ time before any language pack has been loaded yet."""
        from engine.loader import load_language_pack
        try:
            manifest, _ = load_language_pack(os.path.join(self.languages_path, lang))
        except Exception:
            return []
        return manifest.get("node_types", []) if manifest else []

    def build_initial_nodes_for_language(self, lang):
        """
        Phase B3: the node(s) a brand-new file starts with for `lang`.

        Most languages just get today's single empty, unlocked "main"
        node - unchanged from before B3. A language whose
        node_types.json marks some node type both required and
        is_entry_point gets that entry point auto-created and locked
        instead, since such a file can't run/compile without one.

        For C#/Java specifically, the entry point can't sit outside a
        class, so it's wrapped in an auto-created, locked class node
        (see the class-node decision: class is a real code-generation
        construct, scoped narrowly here to this compile requirement,
        kept deliberately separate from Phase D's purely-visual
        category folders).
        """
        node_types = self.get_node_types_for_language(lang)
        entry_type = next(
            (nt for nt in node_types if nt.get("required") and nt.get("is_entry_point")),
            None
        )
        if not entry_type:
            return [make_node("main", node_id="main", blocks=[])]

        entry_node = make_node(
            "Main" if lang == "csharp" else "main",
            node_id=str(uuid.uuid4())[:8],
            blocks=[],
            locked=True,
            node_type_id=entry_type["id"],
            order=1,
        )

        if lang in ("csharp", "java"):
            class_name = "Program" if lang == "csharp" else "Main"
            class_node = make_node(
                class_name, node_id=str(uuid.uuid4())[:8], kind="class",
                child_nodes=[entry_node], locked=True,
            )
            return [class_node]

        return [entry_node]
    
    def load_app_settings(self):
        """Load app settings from JSON file, filling in any missing keys with defaults."""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        settings = dict(DEFAULT_SETTINGS)
        if os.path.exists(APP_SETTINGS_PATH):
            try:
                with open(APP_SETTINGS_PATH, "r") as f:
                    saved = json.load(f)
                settings.update(saved)
            except Exception as e:
                print(f"Failed to load app settings: {e}")
        return settings

    def save_app_settings(self):
        """Save current app settings to JSON file"""
        user_data_dir = os.path.dirname(APP_SETTINGS_PATH)
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        try:
            with open(APP_SETTINGS_PATH, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save app settings: {e}")

    def maybe_notify(self, title, message):
        """Show a 'this succeeded' confirmation popup, unless the user
        has turned those off in Settings. Errors/warnings never go
        through this - only pure success confirmations do."""
        if self.settings.get("show_notifications", True):
            messagebox.showinfo(title, message)
    
    def clear_all(self):
        """Clear all blocks"""
        if not self.project_blocks:
            return
        if messagebox.askyesno("Clear Workspace", f"Remove all {len(self.project_blocks)} blocks?"):
            self.project_blocks.clear()
            self.mark_active_tab_dirty()
            self.refresh_workspace()
