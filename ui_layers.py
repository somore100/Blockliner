"""Layer navigation (Files/Nodes/Blocks/Code), keybinds, panel show/hide, workspace refresh."""
import tkinter as tk
from tkinter import simpledialog
import uuid
from nodes_model import find_node_by_id, make_node, next_order, normalize_orders
from ui_common import BLOCK_CHUNK, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, DEFAULT_SETTINGS, KEYBIND_ACTIONS, TEXT_INPUT_CLASSES, keybind_is_bare
from ui_widgets import BlockWidget


class LayersMixin:
    
    def refresh_node_nav(self):
        """Rebuild the node navigation controls in the workspace header -
        same rebuild-from-scratch pattern as refresh_tab_bar()."""
        for widget in self.node_nav_frame.winfo_children():
            widget.destroy()

        if not getattr(self, "tabs", None):
            return
        if self.view_mode == "files":
            tk.Label(
                self.node_nav_frame, text="\U0001F4C1 All Files \u2014 choose a file",
                bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Button(
                self.node_nav_frame, text="+ New File", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.new_tab
            ).pack(side=tk.LEFT, padx=(0, 10))
            code_toggle_active = self.files_view_code_mode
            tk.Button(
                self.node_nav_frame,
                text=("\U0001F5BC View Canvas" if code_toggle_active else "\U0001F4C4 View Code"),
                bg=(DARK_ACCENT if code_toggle_active else "#3a3a3a"),
                fg=("#ffffff" if code_toggle_active else DARK_FG),
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.toggle_files_view_code_mode
            ).pack(side=tk.LEFT)
            return

        tab = self.tabs[self.active_tab_index]
        nodes = tab.get("nodes", [])

        if self.view_mode == "file":
            path = tab.get("file_view_path", [])
            crumb_parts = [tab["title"]]
            for node_id in path:
                node = find_node_by_id(tab["nodes"], node_id)
                if node:
                    crumb_parts.append(node["name"])
            crumb = "  \u203A  ".join(["\U0001F4C4 " + crumb_parts[0]] + crumb_parts[1:])
            if path:
                tk.Button(
                    self.node_nav_frame, text="\u2190 Back", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.file_view_go_back
                ).pack(side=tk.LEFT, padx=(0, 10))
            else:
                tk.Button(
                    self.node_nav_frame, text="\u2190 Files", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.switch_to_files_view
                ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(
                self.node_nav_frame, text=f"{crumb} \u2014 choose a node",
                bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            tk.Button(
                self.node_nav_frame, text="+ New Node", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_node
            ).pack(side=tk.LEFT, padx=(0, 4))
            tk.Button(
                self.node_nav_frame, text="+ New Category", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_category
            ).pack(side=tk.LEFT, padx=(0, 10))
            code_toggle_active = self.file_view_code_mode
            tk.Button(
                self.node_nav_frame,
                text=("\U0001F5BC View Canvas" if code_toggle_active else "\U0001F4C4 View Code"),
                bg=(DARK_ACCENT if code_toggle_active else "#3a3a3a"),
                fg=("#ffffff" if code_toggle_active else DARK_FG),
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.toggle_file_view_code_mode
            ).pack(side=tk.LEFT)
        else:
            active_node = self.get_active_node(tab)
            crumb = f"\U0001F4C4 {tab['title']}  \u203A  \U0001F9E9 {active_node['name']}"
            tk.Label(
                self.node_nav_frame, text=crumb, bg=DARK_BG, fg="#888888",
                font=("Segoe UI", 9)
            ).pack(side=tk.LEFT, padx=(0, 10))
            # Only worth surfacing "view all nodes" once a file actually
            # has more than one top-level node, or that one node is a
            # class/category with something inside it - otherwise it's
            # a button to a screen that only ever shows the one thing
            # you're already in.
            if len(nodes) > 1 or (len(nodes) == 1 and nodes[0].get("kind") in ("class", "category")):
                tk.Button(
                    self.node_nav_frame, text="\U0001F5C2 Nodes",
                    bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                    font=("Segoe UI", 9), command=self.switch_to_file_view
                ).pack(side=tk.LEFT, padx=(0, 4))
            tk.Button(
                self.node_nav_frame, text="+ New Node", bg="#3a3a3a", fg=DARK_FG,
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                command=self.create_node
            ).pack(side=tk.LEFT)

    def code_visible(self):
        """Is code currently on screen for the current layer?"""
        if self.view_mode == "files":
            return bool(self.files_view_code_mode)
        if self.view_mode == "file":
            return bool(self.file_view_code_mode)
        return self.panels.is_visible("code")

    def goto_layer(self, name):
        """Jump straight to a layer from the layer bar or a keybind.
        files/nodes/blocks pick the layer (staying put if already
        there); 'code' toggles code for whichever layer you're on."""
        if not getattr(self, "tabs", None):
            return
        tab = self.tabs[self.active_tab_index]
        if name == "files":
            if self.view_mode != "files" or self.files_view_code_mode:
                self.switch_to_files_view()
        elif name == "nodes":
            if (self.view_mode != "file" or self.file_view_code_mode
                    or tab.get("file_view_path")):
                self.switch_to_file_view()
        elif name == "blocks":
            if self.view_mode != "node":
                node = self.get_active_node(tab)
                if node is not None:
                    self.open_node(node["id"])
        elif name == "code":
            if self.view_mode == "files":
                self.toggle_files_view_code_mode()
            elif self.view_mode == "file":
                self.toggle_file_view_code_mode()
            else:
                self.toggle_code_panel()
        self.refresh_layer_bar()

    def refresh_layer_bar(self):
        """Restyle the layer bar: the current layer is highlighted, and
        Code is highlighted whenever code is on screen."""
        if not getattr(self, "_layer_buttons", None):
            return
        current = {"files": "files", "file": "nodes", "node": "blocks"}.get(self.view_mode)
        code_on = self.code_visible()
        for key, b in self._layer_buttons.items():
            active = (key == current) or (key == "code" and code_on)
            b.config(bg=DARK_ACCENT if active else "#3a3a3a",
                     fg="#ffffff" if active else DARK_FG,
                     activebackground=DARK_HOVER, activeforeground="#ffffff")

    def get_keybinds(self):
        binds = dict(DEFAULT_SETTINGS["keybinds"])
        saved = self.settings.get("keybinds")
        if isinstance(saved, dict):
            binds.update({k: v for k, v in saved.items() if k in binds and isinstance(v, str)})
        return binds

    def apply_keybinds(self):
        """(Re)bind the layer shortcuts app-wide. Ignored while a modal
        dialog holds the grab, so shortcuts never yank the workspace out
        from under an open dialog."""
        for seq in getattr(self, "_layer_key_seqs", []):
            try:
                self.unbind_all(seq)
            except tk.TclError:
                pass
        self._layer_key_seqs = []
        for action, _label in KEYBIND_ACTIONS:
            seq = self.get_keybinds().get(action)
            if not seq:
                continue
            bare = keybind_is_bare(seq)

            def handler(e, action=action, bare=bare):
                grab = self.grab_current()
                if grab is not None and grab is not self:
                    return None
                if bare:
                    try:
                        focus_class = self.focus_get().winfo_class()
                    except (KeyError, AttributeError, tk.TclError):
                        focus_class = ""
                    if focus_class in TEXT_INPUT_CLASSES:
                        return None  # let the widget use the key
                if action == "layer_up":
                    self.step_layer(-1)
                elif action == "layer_down":
                    self.step_layer(1)
                else:
                    self.goto_layer(action.replace("layer_", ""))
                return "break"

            try:
                self.bind_all(f"<{seq}>", handler)
                self._layer_key_seqs.append(f"<{seq}>")
            except tk.TclError:
                pass

    def step_layer(self, delta):
        """Move one layer toward Files (-1) or Blocks (+1); stops at the
        ends. Code is a toggle, not a layer, so it isn't part of the walk."""
        order = ["files", "nodes", "blocks"]
        current = {"files": "files", "file": "nodes", "node": "blocks"}.get(self.view_mode)
        if current is None:
            return
        target = order[max(0, min(len(order) - 1, order.index(current) + delta))]
        if target != current:
            self.goto_layer(target)

    def switch_to_file_view(self):
        """Always resets to the top level of the file view - a user
        clicking "Nodes" from inside a nested method wants their
        reference frame reset to the whole file, not to resume
        mid-navigation from wherever they last left it."""
        tab = self.tabs[self.active_tab_index]
        tab["file_view_path"] = []
        self.view_mode = "file"
        self.file_view_code_mode = False
        self.refresh_workspace()

    def switch_to_files_view(self):
        """Files layer (top of the three-layer nav model): shows every
        open tab as a box on workspace_canvas, wired by import_module-
        derived file_references. Doesn't touch which tab is "active" -
        active_tab_index still matters for language/palette state - it
        just changes what's drawn. Always resets to the canvas (not the
        code view), mirroring switch_to_file_view()'s reset-to-top
        behavior."""
        self.view_mode = "files"
        self.files_view_code_mode = False
        self.refresh_workspace()
        self.refresh_tab_bar()

    def toggle_files_view_code_mode(self):
        """The Files layer's 'View Code' toggle - swaps the file-boxes
        canvas and the stacked code view, never shows both at once
        ("separate, not split - both would be too messy")."""
        self.files_view_code_mode = not self.files_view_code_mode
        self.refresh_workspace()

    def toggle_file_view_code_mode(self):
        """The Nodes layer's 'View Code' toggle - same idea one level
        down, swaps that file's node/wire canvas for its generated
        code. This is what replaces the old always-visible right-hand
        Generated Code panel at this layer (see
        update_right_panel_visibility) - the panel itself stays
        completely unchanged at the Blocks layer per the settled
        design, and Export/Run/Code->Blocks keep working regardless of
        which of the two is on screen, since they read generated code
        straight from generate_code_for_tab()/self.code_text rather
        than from whatever's currently drawn."""
        self.file_view_code_mode = not self.file_view_code_mode
        self.refresh_workspace()

    def open_file_from_files_view(self, index):
        """Enter a specific file from the Files layer, landing on its
        Nodes layer (the per-tab node/wire canvas) - matches how
        open_node() from the Nodes layer lands you in the Blocks layer.
        Unlike switch_to_tab(), this must work even when index is
        already the active tab (clicking "Open" on the current file
        from the Files layer is a normal thing to do)."""
        if not (0 <= index < len(self.tabs)):
            return
        self.sync_active_tab_state()
        self.active_tab_index = index
        tab = self.tabs[index]
        self.current_language = tab["language"]
        self.project_blocks = self.get_active_node(tab)["blocks"]
        tab["file_view_path"] = []
        self.view_mode = "file"
        self.lang_var.set(self.current_language)
        self.load_blocks_for_language(self.current_language)
        self.load_and_merge_custom_blocks()
        self.refresh_palette()
        self.refresh_workspace()
        self.refresh_tab_bar()

    def file_view_go_back(self):
        tab = self.tabs[self.active_tab_index]
        if tab.get("file_view_path"):
            tab["file_view_path"].pop()
        self.refresh_workspace()

    def get_current_node_list(self, tab):
        """The list of nodes currently shown in file view - either the
        tab's top-level nodes, or a class node's child_nodes if the
        file view has navigated inside one (see file_view_path)."""
        nodes = tab["nodes"]
        for node_id in tab.get("file_view_path", []):
            parent = find_node_by_id(tab["nodes"], node_id)
            nodes = parent["child_nodes"] if parent else []
        return nodes

    def open_node(self, node_id):
        """Enter a node. A function-kind node opens the B1 block editor
        scoped to it. A class-kind or category-kind node has no blocks
        of its own to edit - it holds other nodes - so "opening" it
        instead navigates the file view one level deeper into its
        child_nodes. Category (Phase D) is a pure visual folder with
        zero codegen effect; class actually wraps its children in
        generated code - the two behave identically here since both
        are just organizational containers from the navigation's point
        of view."""
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        if node is None:
            return
        if node.get("kind") in ("class", "category"):
            tab.setdefault("file_view_path", []).append(node_id)
            self.view_mode = "file"
            self.refresh_workspace()
            return
        tab["active_node_id"] = node_id
        self.project_blocks = node["blocks"]
        self.view_mode = "node"
        self.refresh_workspace()

    def create_node(self, pos=None):
        """Add a new, empty function-kind node at the current file-view
        depth (top-level, or inside whichever class/category is
        currently open) and open it directly - naming/organizing
        several nodes is easiest done from inside the one you just
        made, not by round-tripping through the file view."""
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab) if self.view_mode == "file" else tab["nodes"]
        name = simpledialog.askstring(
            "New Node", "Node name:", initialvalue=f"Node {len(target_list) + 1}"
        )
        if name is None:
            return
        name = name.strip() or f"Node {len(target_list) + 1}"
        normalize_orders(tab["nodes"])
        new_node = make_node(name, node_id=str(uuid.uuid4())[:8], blocks=[],
                             order=next_order(tab["nodes"]))
        target_list.append(new_node)
        self.mark_active_tab_dirty()
        if pos is not None:
            # Right-click creation: drop it under the cursor and stay on
            # the canvas so the placement is actually visible.
            new_node["canvas_x"], new_node["canvas_y"] = pos
            self.refresh_workspace()
            return
        self.open_node(new_node["id"])

    def create_category(self, pos=None):
        """Phase D: add a new, empty category node (a pure visual
        folder - zero codegen effect, see make_node's docstring) at the
        current file-view depth, and navigate straight into it via
        open_node so nodes can be added to it immediately. Only
        available from file view - a category is an organizational
        concept on the canvas, not something reachable from inside a
        function's block editor."""
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab)
        name = simpledialog.askstring(
            "New Category", "Category name:", initialvalue=f"Category {len(target_list) + 1}"
        )
        if name is None:
            return
        name = name.strip() or f"Category {len(target_list) + 1}"
        new_category = make_node(
            name, node_id=str(uuid.uuid4())[:8], kind="category", child_nodes=[]
        )
        target_list.append(new_category)
        self.mark_active_tab_dirty()
        if pos is not None:
            new_category["canvas_x"], new_category["canvas_y"] = pos
            self.refresh_workspace()
            return
        self.open_node(new_category["id"])

    def toggle_palette(self):
        """Collapse / expand the left block palette (edge-strip click)."""
        self.panels.toggle("palette")

    def _on_panel_visibility_changed(self, panel_id, visible):
        if panel_id == "palette":
            self.palette_strip_glyph.config(text="\u25c2" if visible else "\u25b8")
        elif panel_id == "code":
            self.code_strip_glyph.config(text="\u25b8" if visible else "\u25c2")
            self.refresh_layer_bar()

    def _code_strip_hover(self, on):
        bg = DARK_BORDER if on else DARK_PANEL
        self.code_strip.config(bg=bg)
        self.code_strip_glyph.config(bg=bg, fg="#ffffff" if on else "#888888")

    def _sync_code_strip(self):
        """Show the right strip only at the Blocks layer (the only place
        the code panel exists); its glyph points at what a click does."""
        want = (self.view_mode == "node")
        if want and not self._code_strip_shown:
            self.code_strip.pack(side=tk.RIGHT, fill=tk.Y, padx=(3, 0),
                                before=self.panels.paned)
            self._code_strip_shown = True
        elif not want and self._code_strip_shown:
            self.code_strip.pack_forget()
            self._code_strip_shown = False
        self.code_strip_glyph.config(
            text="\u25b8" if self.panels.is_visible("code") else "\u25c2")

    def can_drop_block_at(self, x_root, y_root):
        """True if a palette block dropped at this screen position should
        be added: Blocks layer only, and only over the workspace."""
        if self.view_mode != "node":
            return False
        try:
            w = self.winfo_containing(x_root, y_root)
        except (tk.TclError, KeyError):
            return False
        canvas = str(self.workspace_canvas)
        while w is not None:
            if str(w) == canvas:
                return True
            w = getattr(w, "master", None)
        return False

    def _palette_strip_hover(self, on):
        bg = DARK_BORDER if on else DARK_PANEL
        self.palette_strip.config(bg=bg)
        self.palette_strip_glyph.config(bg=bg, fg="#ffffff" if on else "#888888")

    def toggle_code_panel(self):
        """User show/hide of the Generated Code panel (Blocks layer). Kept
        as a flag because update_right_panel_visibility() runs on every
        refresh and would otherwise force the panel back on."""
        self._code_panel_user_hidden = not getattr(self, "_code_panel_user_hidden", False)
        self.update_right_panel_visibility()

    def update_right_panel_visibility(self):
        """The always-visible right-hand Generated Code panel is now
        exclusively a Blocks-layer (view_mode == "node") feature, per
        the settled design - the Files and Nodes layers each got their
        own in-canvas 'View Code' toggle instead (render_files_code_view/
        render_file_code_view), so showing this panel at the same time
        would be exactly the redundant split the toggle design was
        chosen to avoid. Hiding it never affects Export/Run/Code->Blocks
        - self.code_text is kept current regardless (update_generated_code()
        now runs unconditionally in refresh_workspace), a Tk widget's
        .get() works whether or not it's currently on screen."""
        self.panels.set_visible(
            "code",
            self.view_mode == "node" and not getattr(self, "_code_panel_user_hidden", False))
        self._sync_code_strip()

    def refresh_workspace(self):
        """Refresh the visual workspace - either the file-level node
        boxes (view_mode == "file") or the block editor for whichever
        node is currently active (view_mode == "node", the default and
        today's exact original behavior when a tab has only one node)."""
        self.recompute_references()
        self.recompute_file_references()
        # Kept unconditional (not just for view_mode == "file"/"node")
        # so self.code_text - the data Export/Run/Code->Blocks actually
        # read - stays current for the active tab no matter which layer
        # or toggle state is on screen; see update_right_panel_visibility.
        self.update_generated_code()
        self.update_right_panel_visibility()

        self._more_footer = None   # before destroying: scroll events must not touch dead widgets
        for widget in self.workspace_frame.winfo_children():
            widget.destroy()
        # Phase C2's node boxes/wires live directly on workspace_canvas
        # (not inside workspace_frame, so they can be freely positioned
        # instead of pack()-stacked) - clear them here unconditionally
        # so switching to the block editor view never leaves stale
        # boxes/wires behind.
        self.workspace_canvas.delete("fileview")

        # Tk canvas window items (like the one embedding workspace_frame)
        # always paint on top of drawn items (lines/ovals) regardless of
        # creation order or raise/lower - and an empty Frame doesn't
        # reliably shrink its own requested height back down once
        # something bigger (e.g. the "empty state" message) has been
        # packed into it. Left alone, that stale height silently
        # occludes every wire drawn on the canvas beneath it. Pinning
        # it to 1px whenever nothing is meant to be inside
        # workspace_frame (file view - the "Back" button lives in the
        # header nav instead, see refresh_node_nav) sidesteps the
        # problem entirely; reverting to "" lets it size normally again
        # for the block editor or either layer's code view.
        if self.view_mode == "files" and self.files_view_code_mode:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)
        elif self.view_mode == "file" and self.file_view_code_mode:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)
        elif self.view_mode in ("file", "files"):
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=1)
        else:
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, height=0)

        self.refresh_node_nav()
        self.refresh_layer_bar()

        if self.view_mode == "files":
            if self.files_view_code_mode:
                self.render_files_code_view()
            else:
                self.render_files_view()
            self.block_count_label.config(text="")
            return

        if self.view_mode == "file":
            if self.file_view_code_mode:
                self.render_file_code_view()
            else:
                self.render_file_view()
            self.block_count_label.config(text="")
            return

        self._more_footer = None
        if not self.project_blocks:
            self.show_empty_state()
            self._win_list = None
        else:
            self._render_block_window()

        count = len(self.project_blocks)
        label = f"{count} block{'s' if count != 1 else ''}"
        if self._win_list is self.project_blocks and (self._win_start > 0 or self._win_end < count):
            label += f" (showing {self._win_start + 1}-{self._win_end})"
        self.block_count_label.config(text=label)

    # ---- lazy block rendering (Blocks layer) ------------------------------
    # Only a window [_win_start, _win_end) of the top-level blocks is built
    # as widgets (Tk layout cost grows steeply with widget count). Block
    # indexes stay absolute, so edit/move/delete are unaffected. The window
    # resets to the top whenever project_blocks becomes a different list
    # (node/tab switch, code-view commit); it persists across refreshes of
    # the same list, so editing block 300 doesn't snap you back to block 1.

    def _clamp_block_window(self):
        blocks, n = self.project_blocks, len(self.project_blocks)
        prev = getattr(self, "_win_list", None)
        if prev is not blocks:
            self._win_list, self._win_start, self._win_end, self._win_len = blocks, 0, min(n, BLOCK_CHUNK), n
            return
        start, end = self._win_start, self._win_end
        if n > self._win_len and end >= self._win_len:
            end = n                      # was viewing the tail: new blocks join the window
        if start >= n:                   # the whole window was deleted/shrunk away: show the tail
            start, end = max(0, n - BLOCK_CHUNK), n
        end = min(end, n)
        self._win_start, self._win_end, self._win_len = start, end, n

    def reveal_block(self, index, to_tail=False):
        """Make sure top-level block `index` falls inside the rendered window
        (call before refresh_workspace). to_tail: show the last chunk instead."""
        blocks, n = self.project_blocks, len(self.project_blocks)
        if getattr(self, "_win_list", None) is not blocks:
            self._win_list, self._win_start, self._win_end, self._win_len = blocks, 0, min(n, BLOCK_CHUNK), n
        if to_tail:
            self._win_start, self._win_end = max(0, n - BLOCK_CHUNK), n
            self._scroll_to_end_pending = True
        else:
            self._win_start = min(self._win_start, index)
            self._win_end = max(self._win_end, index + 1)

    def _make_block_widget(self, i):
        block_id, params = self.project_blocks[i]
        block_module = self.blocks.get(block_id)
        if not block_module:
            return None
        w = BlockWidget(self.workspace_frame, block_id, block_module,
                        params if isinstance(params, dict) else dict(params),
                        i, self.project_blocks, self)
        return w

    def _render_block_window(self):
        self._clamp_block_window()
        if self._win_start > 0:
            self._earlier_row = self._make_window_row(
                f"\u25b2 {self._win_start} earlier block{'s' if self._win_start != 1 else ''}",
                [("Show earlier", self._show_earlier_blocks)])
            self._earlier_row.pack(fill=tk.X, pady=4, padx=10)
        for i in range(self._win_start, self._win_end):
            w = self._make_block_widget(i)
            if w is not None:
                w.pack(fill=tk.X, pady=4, padx=10)
        self._update_more_footer()
        if getattr(self, "_scroll_to_end_pending", False):
            self._scroll_to_end_pending = False
            self.after_idle(lambda: self.workspace_canvas.yview_moveto(1.0))

    def _make_window_row(self, text, buttons):
        row = tk.Frame(self.workspace_frame, bg=DARK_BG)
        tk.Label(row, text=text, bg=DARK_BG, fg="#888888", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(4, 10))
        for label, cmd in buttons:
            tk.Button(row, text=label, bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT,
                      cursor="hand2", font=("Segoe UI", 9), command=cmd).pack(side=tk.LEFT, padx=3)
        return row

    def _update_more_footer(self):
        """(Re)create the 'N more blocks' footer, or remove it when done."""
        old = getattr(self, "_more_footer", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
            self._more_footer = None
        remaining = len(self.project_blocks) - self._win_end
        if remaining > 0:
            self._more_footer = self._make_window_row(
                f"\u25bc {remaining} more block{'s' if remaining != 1 else ''}",
                [(f"Show next {min(BLOCK_CHUNK, remaining)}", self._show_more_blocks),
                 ("Show all", lambda: self._show_more_blocks(all_remaining=True))])
            self._more_footer.pack(fill=tk.X, pady=4, padx=10)

    def _show_more_blocks(self, all_remaining=False):
        """Extend the window downward IN PLACE (no rebuild of what's shown)."""
        if self.view_mode != "node" or getattr(self, "_win_list", None) is not self.project_blocks:
            return
        n = len(self.project_blocks)
        new_end = n if all_remaining else min(n, self._win_end + BLOCK_CHUNK)
        if new_end <= self._win_end:
            return
        if getattr(self, "_more_footer", None) is not None:
            self._more_footer.destroy()
            self._more_footer = None
        for i in range(self._win_end, new_end):
            w = self._make_block_widget(i)
            if w is not None:
                w.pack(fill=tk.X, pady=4, padx=10)
        self._win_end = new_end
        self._update_more_footer()
        count = len(self.project_blocks)
        label = f"{count} block{'s' if count != 1 else ''}"
        if self._win_start > 0 or self._win_end < count:
            label += f" (showing {self._win_start + 1}-{self._win_end})"
        self.block_count_label.config(text=label)

    def _show_earlier_blocks(self):
        if self.view_mode != "node" or getattr(self, "_win_list", None) is not self.project_blocks:
            return
        self._win_start = max(0, self._win_start - BLOCK_CHUNK)
        self.refresh_workspace()

    def _on_workspace_yscroll(self, first, last):
        """Scrollbar feed + auto-load the next chunk when scrolled to the bottom."""
        self.workspace_scrollbar.set(first, last)
        if (getattr(self, "_more_footer", None) is None or self.view_mode != "node"
                or getattr(self, "_auto_loading", False)):
            return
        try:
            near_bottom = float(last) >= 0.97
        except (TypeError, ValueError):
            return
        if near_bottom:
            self.after_idle(self._auto_load_more)

    def _auto_load_more(self):
        if getattr(self, "_auto_loading", False) or getattr(self, "_more_footer", None) is None:
            return
        self._auto_loading = True
        try:
            if self._more_footer.winfo_exists() and float(self.workspace_canvas.yview()[1]) >= 0.97:
                self._show_more_blocks()
                self.update_idletasks()   # settle the scrollregion before re-arming
        finally:
            self._auto_loading = False
