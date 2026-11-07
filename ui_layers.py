"""Layer navigation (Files/Nodes/Blocks/Code), keybinds, panel show/hide, workspace refresh."""
import tkinter as tk
from tkinter import simpledialog
import uuid
import doc_types
import ui_node
from editors import EditorContext
from nodes_model import find_node_by_id, make_node, next_order, normalize_orders
from ui_common import BLOCK_CHUNK, DARK_ACCENT, DARK_BG, DARK_BORDER, DARK_FG, DARK_HOVER, DARK_PANEL, DEFAULT_SETTINGS, KEYBIND_ACTIONS, TEXT_INPUT_CLASSES, keybind_is_bare
from ui_widgets import BlockWidget
from ui_multiopen import NodeMarkerRow
from multi_open import NODE_MARK


class LayersMixin:
    
    def breadcrumb_segments(self):
        """[(label, action | None)] for the trail; the last item is where
        you are (no action). Each action jumps straight to that level."""
        segs = [("\U0001F4C1 Files", self.switch_to_files_view)]
        if self.view_mode == "files" or not getattr(self, "tabs", None):
            segs[0] = (segs[0][0], None)
            return segs
        tab = self.tabs[self.active_tab_index]
        path = tab.get("file_view_path", []) if self.view_mode == "file" else []
        segs.append(("\U0001F4C4 " + tab["title"], lambda: self.goto_file_level(0)))
        if self.view_mode == "node":
            # open_node never leaves a class path set, so rebuild it from the node's owner
            path = self.owner_path(tab, tab.get("active_node_id"))
        for depth, node_id in enumerate(path, 1):
            node = find_node_by_id(tab["nodes"], node_id)
            if node:
                segs.append((node["name"], lambda d=depth: self.goto_file_level(d)))
        if self.view_mode == "node":
            together = self.multi_crumb()
            if together:
                segs.append((together, None))
            else:
                segs.append(("\U0001F9E9 " + self.get_active_node(tab)["name"], None))
                spec = self.current_editor()
                if spec is not None:
                    segs.append((spec.title, None))
        segs[-1] = (segs[-1][0], None)
        return segs

    def owner_path(self, tab, node_id):
        """Ids of the class/category nodes containing node_id, outermost first."""
        def walk(nodes, trail):
            for n in nodes:
                if n.get("id") == node_id:
                    return trail
                found = walk(n.get("child_nodes") or [], trail + [n["id"]])
                if found is not None:
                    return found
            return None
        return walk(tab["nodes"], []) or []

    def goto_file_level(self, depth):
        """Show the Nodes layer at `depth` levels into the file (0 = top)."""
        tab = self.tabs[self.active_tab_index]
        full = tab.get("file_view_path", []) if self.view_mode == "file" else self.owner_path(tab, tab.get("active_node_id"))
        tab["file_view_path"] = list(full[:depth])
        self.view_mode = "file"
        self.file_view_code_mode = False
        self.refresh_workspace()

    def refresh_breadcrumb(self):
        for widget in self.crumb_bar.winfo_children():
            widget.destroy()
        segs = self.breadcrumb_segments()
        for i, (label, action) in enumerate(segs):
            if i:
                tk.Label(self.crumb_bar, text="›", bg=DARK_PANEL, fg="#666666",
                         font=("Segoe UI", 10)).pack(side=tk.LEFT)
            if action is None:
                tk.Label(self.crumb_bar, text=label, bg=DARK_PANEL, fg="#ffffff",
                         font=("Segoe UI", 9, "bold"), padx=6).pack(side=tk.LEFT)
            else:
                b = tk.Label(self.crumb_bar, text=label, bg=DARK_PANEL, fg=DARK_FG,
                             font=("Segoe UI", 9), padx=6, cursor="hand2")
                b.pack(side=tk.LEFT)
                b.bind("<Button-1>", lambda e, a=action: a())
                b.bind("<Enter>", lambda e, w=b: w.config(fg=DARK_ACCENT))
                b.bind("<Leave>", lambda e, w=b: w.config(fg=DARK_FG))

    def refresh_node_nav(self):
        """Rebuild the node navigation controls in the workspace header -
        same rebuild-from-scratch pattern as refresh_tab_bar()."""
        self.refresh_breadcrumb()
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
            ).pack(side=tk.LEFT, padx=(0, 4))
            if not self.files_view_code_mode:
                tk.Button(
                    self.node_nav_frame, text="\u25ad New Group", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.add_group_in_view
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
                self.node_nav_frame, text="choose a node",
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
            ).pack(side=tk.LEFT, padx=(0, 4))
            if not self.file_view_code_mode:
                tk.Button(
                    self.node_nav_frame, text="\u25ad New Group", bg="#3a3a3a", fg=DARK_FG,
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.add_group_in_view
                ).pack(side=tk.LEFT, padx=(0, 10))
                if len(self.selected_nodes()) >= 2:
                    tk.Button(
                        self.node_nav_frame, text=self.group_selected_label(),
                        bg="#3a3a3a", fg=DARK_FG, relief=tk.FLAT, cursor="hand2",
                        font=("Segoe UI", 9), command=self.group_selected_nodes
                    ).pack(side=tk.LEFT, padx=(0, 10))
                if len(self.selected_function_nodes()) >= 2:
                    tk.Button(
                        self.node_nav_frame, text="\u29c9 " + self.open_together_label(),
                        bg=DARK_ACCENT, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
                        font=("Segoe UI", 9), command=self.open_selected_nodes
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
            # Only worth surfacing "view all nodes" once a file actually
            # has more than one top-level node, or that one node is a
            # class/category with something inside it - otherwise it's
            # a button to a screen that only ever shows the one thing
            # you're already in.
            active_node = self.get_active_node(tab)
            if ui_node.is_ui_node(active_node) and ui_node.is_detached(active_node):
                tk.Button(
                    self.node_nav_frame, text="\u21a9 Back to designer", bg=DARK_ACCENT, fg="#ffffff",
                    relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                    command=self.reattach_ui_node
                ).pack(side=tk.LEFT, padx=(0, 4))
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
        self._behaviour_id = None                 # a UI window opens in the designer, not in Behaviour
        self.selected_nodes().clear()
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
            self.refresh_after_node_added(new_node, target_list)
            return
        self.open_node(new_node["id"])

    STARTER_NODES = (("function", "Empty function"), ("class", "Class"),
                     ("category", "Category"), ("raw", "Raw code"),
                     ("ui", "UI window"), ("ui_popup", "UI popup window"))

    def create_starter_node(self, key, pos, wire_from=None):
        """Create a ready-made node at pos on the Nodes layer without a
        name prompt (rename later from its menu). Function-type nodes
        are wired from wire_from when given."""
        tab = self.tabs[self.active_tab_index]
        target_list = self.get_current_node_list(tab) if self.view_mode == "file" else tab["nodes"]
        n = len(target_list) + 1
        normalize_orders(tab["nodes"])
        if key in ("ui", "ui_popup"):
            node = self.new_ui_node(tab, f"UI {n}", popup=key == "ui_popup")
            if node is None:
                return None
            wire_from = None
        elif key == "class":
            node = make_node(f"Class {n}", node_id=str(uuid.uuid4())[:8], kind="class", child_nodes=[])
        elif key == "category":
            node = make_node(f"Category {n}", node_id=str(uuid.uuid4())[:8], kind="category", child_nodes=[])
        else:
            blocks = []
            if key == "raw":
                bid = self.get_raw_code_block_id(self.current_language)
                pn = self.get_raw_code_param_name(bid)
                if bid and pn:
                    blocks = [(bid, {pn: ""})]
            name = f"Raw code {n}" if key == "raw" else f"Function {n}"
            node = make_node(name, node_id=str(uuid.uuid4())[:8], blocks=blocks,
                             order=next_order(tab["nodes"]))
        node["canvas_x"], node["canvas_y"] = pos
        target_list.append(node)
        self.regenerate_ui_nodes()
        self.mark_active_tab_dirty()
        if wire_from is not None and node.get("kind", "function") == "function":
            self.add_wire_by_drag(wire_from, node["id"])   # also refreshes
        else:
            self.refresh_after_node_added(node, target_list)
        return node

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
            self.refresh_after_node_added(new_category, target_list)
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

    def _top_level_block_widgets(self):
        """Rendered top-level BlockWidgets in on-screen order. Nested
        children are grandchildren (inside their container's widget), and
        the window rows aren't BlockWidgets, so neither is included.
        Not filtered by winfo_ismapped: Tk unmaps canvas windows that are
        scrolled out of view, but their layout (winfo_y) is still valid."""
        return [w for w in self.workspace_frame.winfo_children()
                if isinstance(w, (BlockWidget, NodeMarkerRow)) and w.winfo_exists()]

    def drop_target(self, y_root):
        """Where a palette block released at screen y should go.
        Returns (insert_at, line_y): insert_at is an ABSOLUTE index into
        project_blocks (BlockWidget.index, so the lazy window is fine) or
        None to append at the very end; line_y is the indicator's y inside
        workspace_frame. Above a block's vertical midpoint = before it;
        below the last rendered block (or an empty workspace) = append.
        Works in workspace_frame coordinates, so scrolling doesn't matter."""
        y = y_root - self.workspace_frame.winfo_rooty()
        widgets = self._top_level_block_widgets()
        for w in widgets:
            if y < w.winfo_y() + w.winfo_height() / 2:
                return w.index, max(0, w.winfo_y() - 4)
        if widgets:
            last = widgets[-1]
            return None, last.winfo_y() + last.winfo_height() + 1
        return None, 4

    def show_drop_indicator(self, x_root, y_root):
        """Palette drag feedback: a thin line where the block would land.
        (None, None) removes it."""
        line = getattr(self, "_drop_line", None)
        if x_root is None:
            if line is not None:
                try:
                    line.destroy()
                except tk.TclError:
                    pass
            self._drop_line = None
            return
        _idx, y = self.drop_target(y_root)
        try:
            if line is None or not line.winfo_exists():
                line = tk.Frame(self.workspace_frame, bg=DARK_ACCENT, height=3)
                self._drop_line = line
            line.place(x=10, y=y, relwidth=1.0, width=-20, height=3)
            line.lift()
        except tk.TclError:
            self._drop_line = None

    def add_block_from_drop(self, block_module, x_root, y_root):
        """Palette drop: same add flow as a click, but inserted where the
        block was dropped instead of appended."""
        insert_at, _y = self.drop_target(y_root)
        self.add_block_to_workspace(block_module, insert_at=insert_at)

    def move_block_to(self, src, insert_at):
        """Move top-level block `src` so it lands before absolute index
        `insert_at` (None = the very end), the same convention as
        drop_target. Returns False for a no-op (same place / bad index).
        Moving down compensates for the removal of the source first."""
        blocks = self.project_blocks
        n = len(blocks)
        if not (0 <= src < n):
            return False
        dest = n if insert_at is None else max(0, min(insert_at, n))
        if dest > src:
            dest -= 1
        if dest == src:
            return False
        blocks.insert(dest, blocks.pop(src))
        self.reveal_block(dest)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return True

    def block_drag_feedback(self, src, x_root, y_root):
        """Landing line for a workspace block being dragged; hidden when
        outside the workspace or when dropping there would change nothing."""
        if x_root is None or not self.can_drop_block_at(x_root, y_root):
            self.show_drop_indicator(None, None)
            return
        idx, _y = self.drop_target(y_root)
        if (len(self.project_blocks) if idx is None else idx) in (src, src + 1):
            self.show_drop_indicator(None, None)
        else:
            self.show_drop_indicator(x_root, y_root)

    def drop_block_reorder(self, src, x_root, y_root):
        """Release of a dragged workspace block: reorder if over the workspace."""
        if not self.can_drop_block_at(x_root, y_root):
            return False
        idx, _y = self.drop_target(y_root)
        return self.move_block_to(src, idx)

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
        self._sync_palette_for_layer()

    def _sync_palette_for_layer(self):
        """The block palette is useless on the Nodes layer (view_mode ==
        "file"): hide it and its edge strip there, and put both back the
        way they were when you leave."""
        on_nodes = (self.view_mode in ("file", "files")) or self.current_editor() is not None
        hidden = getattr(self, "_palette_hidden_by_layer", False)
        if on_nodes and not hidden:
            self._palette_was_visible = self.panels.is_visible("palette")
            self.panels.hide("palette")
            self.palette_strip.pack_forget()
            self._palette_hidden_by_layer = True
        elif not on_nodes and hidden:
            self.palette_strip.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3),
                                    before=self.panels.paned)
            self.panels.set_visible("palette", getattr(self, "_palette_was_visible", True))
            self._palette_hidden_by_layer = False

    def editor_context(self):
        """What is open, for the editor registry."""
        facet = self.view_mode
        ref = None
        if self.view_mode == "node":
            node = self.designer_node()
            if node is not None:
                facet, ref = "ui-node", node["id"]
        return EditorContext(doc_types.CODEBUILDER, facet, ref)

    def current_editor(self):
        """The registered editor that owns the centre panel now, or None
        (Code Builder's own canvas and block views)."""
        return self.editor_registry.resolve(self.editor_context())

    def show_editor_frame(self, on):
        """Swap the scrolling canvas for the editor frame (or back). The frame
        takes the canvas's place in the packing order."""
        if on == getattr(self, "_editor_frame_shown", False):
            return
        self._editor_frame_shown = on
        if on:
            self.workspace_canvas.pack_forget()
            self.workspace_scrollbar.pack_forget()
            self.editor_frame.pack(fill=tk.BOTH, expand=True, after=self.crumb_bar)
        else:
            self.editor_frame.pack_forget()
            self.workspace_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, after=self.crumb_bar)
            self.workspace_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, after=self.crumb_bar)

    def refresh_workspace(self):
        """Refresh the visual workspace - either the file-level node
        boxes (view_mode == "file") or the block editor for whichever
        node is currently active (view_mode == "node", the default and
        today's exact original behavior when a tab has only one node)."""
        self.multi_check()
        self.recompute_references()
        self.recompute_file_references()
        self._reset_block_view = self.view_mode == "node" and getattr(self, "_rendered_mode", None) != "node"
        self._rendered_mode = self.view_mode
        # Kept unconditional (not just for view_mode == "file"/"node")
        # so self.code_text - the data Export/Run/Code->Blocks actually
        # read - stays current for the active tab no matter which layer
        # or toggle state is on screen; see update_right_panel_visibility.
        self.regenerate_ui_nodes()
        self.update_generated_code()
        self.update_right_panel_visibility()

        self._more_footer = None   # before destroying: scroll events must not touch dead widgets
        self._selected_block_set = set()               # block numbers shift on every redraw
        self._update_multi_bar()
        for widget in self.workspace_frame.winfo_children():
            widget.destroy()
        for widget in self.editor_frame.winfo_children():
            widget.destroy()
        # Phase C2's node boxes/wires live directly on workspace_canvas
        # (not inside workspace_frame, so they can be freely positioned
        # instead of pack()-stacked) - clear them here unconditionally
        # so switching to the block editor view never leaves stale
        # boxes/wires behind.
        # Deleting a window item does not destroy its widget: destroy the
        # old boxes too (after the current event - a box's own handler may
        # be what triggered this refresh), or they pile up for ever.
        old_boxes = self._canvas_box_widgets()
        self._fileview_boxes, self._filesview_boxes = {}, {}
        if old_boxes:
            self.after_idle(lambda ws=old_boxes: [w.destroy() for w in ws if w.winfo_exists()])
        self.workspace_canvas.delete("fileview")
        self.workspace_canvas.delete("grid")
        self._wire_kinds_seen = set()
        self._update_wire_legend()      # no wires yet: removes the old key

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
        # Even 1px of it hid the y=0 axis of the coordinate grid for the
        # frame's whole width, so on the canvas layers it is hidden outright.
        wid = self.workspace_frame_window_id
        if self.view_mode == "files" and self.files_view_code_mode:
            self.workspace_canvas.itemconfigure(wid, height=0, state="normal")
        elif self.view_mode == "file" and self.file_view_code_mode:
            self.workspace_canvas.itemconfigure(wid, height=0, state="normal")
        elif self.view_mode in ("file", "files"):
            self.workspace_canvas.itemconfigure(wid, height=1, state="hidden")
        else:
            self.workspace_canvas.itemconfigure(wid, height=0, state="normal")

        editor = self.current_editor()
        self.show_editor_frame(editor is not None)
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
        self.after_idle(self._reveal_block_view)
        if editor is not None:
            editor.create(self).render()
            self.block_count_label.config(text=editor.title)
            return
        if self.behaviour_active():
            self.render_behaviour_view()
            return
        if not self.project_blocks:
            self.show_empty_state()
            self._win_list = None
        else:
            self._render_block_window()

        count = len(self.project_blocks)
        shown = self.real_block_count()
        label = f"{shown} block{'s' if shown != 1 else ''}"
        if self._win_list is self.project_blocks and (self._win_start > 0 or self._win_end < count):
            label += f" (showing {self._win_start + 1}-{self._win_end})"
        self.block_count_label.config(text=label)

    def _reveal_block_view(self):
        """The canvas is unconfined (the Nodes layer pans it freely), so a pan
        offset carries over into the Blocks layer, whose content sits at
        (0, 0) - the blocks were built but scrolled out of sight. Nothing
        scrolls sideways here: always back to x = 0; back to the top when the
        layer was just entered or the content is no longer in view."""
        if self.view_mode != "node":
            return
        c = self.workspace_canvas
        try:
            x0, y0 = c.canvasx(0), c.canvasy(0)
            h = c.winfo_height()
            content_h = self.workspace_frame.winfo_reqheight()
        except tk.TclError:
            return
        top = bool(getattr(self, "_reset_block_view", False)) or y0 >= content_h or y0 + h <= 0
        self._reset_block_view = False
        if x0 != 0 or top:
            self._set_view_origin(0, 0 if top else y0)
            c.configure(scrollregion=c.bbox("all"))

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
        if block_id == NODE_MARK:
            return self.make_node_marker_row(i)
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
        old_start = self._win_start
        new_start = max(0, old_start - BLOCK_CHUNK)
        if new_start >= old_start:
            return
        earlier = getattr(self, "_earlier_row", None)
        slaves = [w for w in self.workspace_frame.pack_slaves() if w is not earlier]
        if not slaves:
            self._win_start = new_start
            self.refresh_workspace()
            return
        # Prepend IN PLACE and keep the block that was on screen where it is.
        first = slaves[0]
        c = self.workspace_canvas
        self.update_idletasks()
        y_before = first.winfo_y() - c.canvasy(0)
        self._win_start = new_start
        for i in range(new_start, old_start):
            w = self._make_block_widget(i)
            if w is not None:
                w.pack(fill=tk.X, pady=4, padx=10, before=first)
        if earlier is not None:
            earlier.destroy()
            self._earlier_row = None
        if new_start > 0:
            self._earlier_row = self._make_window_row(
                f"\u25b2 {new_start} earlier block{'s' if new_start != 1 else ''}",
                [("Show earlier", self._show_earlier_blocks)])
            self._earlier_row.pack(fill=tk.X, pady=4, padx=10, before=self.workspace_frame.pack_slaves()[0])
        self.update_idletasks()
        try:
            top, bottom = (float(v) for v in str(c.cget("scrollregion")).split()[1::2])
            if bottom > top:
                c.yview_moveto((first.winfo_y() - y_before - top) / (bottom - top))
        except (ValueError, tk.TclError):
            pass
        count = len(self.project_blocks)
        label = f"{count} block{'s' if count != 1 else ''}"
        if self._win_start > 0 or self._win_end < count:
            label += f" (showing {self._win_start + 1}-{self._win_end})"
        self.block_count_label.config(text=label)

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
