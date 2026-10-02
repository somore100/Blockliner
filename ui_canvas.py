"""Node/file canvas rendering, dragging and wires."""
import tkinter as tk
from nodes_model import find_node_by_id, normalize_orders
from ui_common import BLOCK_BG, CATEGORY_COLORS, DARK_BORDER, DARK_FG, get_block_attr


class CanvasMixin:

    def render_files_view(self):
        """Files layer: every open tab as a draggable box on
        workspace_canvas, reusing C2's box/wire canvas mechanics one
        level up - files as boxes instead of nodes, wires resolved
        from import_module blocks (recompute_file_references) the same
        way func_call resolves node-to-node in the Nodes layer. Shares
        the "fileview" canvas tag with the Nodes layer's own boxes/
        wires purely so _update_fileview_scrollregion's bbox lookup
        works unchanged for either layer."""
        self._filesview_boxes = {}
        self.workspace_canvas.delete("wire_drag_temp")

        if not self.tabs:
            self.show_empty_state()
            return

        self.assign_default_tab_canvas_positions()

        for index, tab in enumerate(self.tabs):
            self.create_filesview_file_box(index, tab)

        self.workspace_frame.update_idletasks()
        self.draw_file_wires()
        self._update_fileview_scrollregion()

    def create_filesview_file_box(self, index, tab):
        """Build one tab's draggable box and place it on
        workspace_canvas at its stored (canvas_x, canvas_y). Visually
        distinct from a Nodes-layer node box (blue accent, file icon)
        so the two layers are never mistaken for each other in a
        screenshot. No wire-drag port here - unlike func_call wires
        (C3), an import wire is created by typing into an
        import_module block's module field, not by dragging."""
        box_color = "#2a5a8a"
        box = tk.Frame(
            self.workspace_canvas, bg=BLOCK_BG, highlightthickness=2,
            highlightbackground=DARK_BORDER
        )

        def _open(_e=None, idx=index):
            self.open_file_from_files_view(idx)

        header = tk.Frame(box, bg=box_color, height=36, cursor="fleur")
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        label_text = tab["title"] + (" \u25CF" if tab.get("dirty") else "")
        name_label = tk.Label(
            header, text=f"\U0001F4C4 {label_text}",
            bg=box_color, fg="#ffffff",
            font=("Segoe UI", 10, "bold"), anchor="w", cursor="fleur"
        )
        name_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        body = tk.Frame(box, bg=BLOCK_BG)
        body.pack(fill=tk.X, padx=10, pady=8)
        node_count = len(tab.get("nodes", []))
        tk.Label(
            body, text=f"{node_count} node{'s' if node_count != 1 else ''} \u2022 {tab['language']}",
            bg=BLOCK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Button(
            body, text="Open \u2192", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=_open
        ).pack(side=tk.RIGHT)

        win_id = self.workspace_canvas.create_window(
            tab["canvas_x"], tab["canvas_y"], anchor="nw", window=box,
            tags=("fileview", "file_box")
        )
        self._filesview_boxes[index] = (win_id, box)
        self._bind_context_recursive(
            box, lambda e, idx=index: self._on_file_box_right_click(e, idx))

        # Same press/motion/release-with-threshold drag pattern as
        # create_fileview_node_box(), operating on the tab's canvas_x/
        # canvas_y instead of a node's.
        drag_state = {"dragging": False, "start_x": 0, "start_y": 0,
                      "tab_x0": 0, "tab_y0": 0}

        def _press(e, idx=index):
            drag_state["dragging"] = False
            drag_state["start_x"] = e.x_root
            drag_state["start_y"] = e.y_root
            if not (0 <= idx < len(self.tabs)):
                return
            t = self.tabs[idx]
            drag_state["tab_x0"] = t["canvas_x"]
            drag_state["tab_y0"] = t["canvas_y"]

        def _motion(e, idx=index):
            dx = e.x_root - drag_state["start_x"]
            dy = e.y_root - drag_state["start_y"]
            if not drag_state["dragging"] and (abs(dx) > 4 or abs(dy) > 4):
                drag_state["dragging"] = True
            if not drag_state["dragging"]:
                return
            if not (0 <= idx < len(self.tabs)):
                return
            t = self.tabs[idx]
            new_x = drag_state["tab_x0"] + dx
            new_y = drag_state["tab_y0"] + dy
            t["canvas_x"], t["canvas_y"] = new_x, new_y
            wid, _ = self._filesview_boxes.get(idx, (None, None))
            if wid is not None:
                self.workspace_canvas.coords(wid, new_x, new_y)
            self.draw_file_wires()

        def _release(e, idx=index):
            drag_state["dragging"] = False
            self._update_fileview_scrollregion()

        for w in (header, name_label):
            w.bind("<ButtonPress-1>", _press)
            w.bind("<B1-Motion>", _motion)
            w.bind("<ButtonRelease-1>", _release)
            w.bind("<Double-Button-1>", _open)

    def draw_file_wires(self):
        """Files-layer equivalent of draw_wires(): redraw every derived
        import edge (tab['file_references']) as a curved connector
        between two file boxes. Pure rendering, never mutates."""
        self.workspace_canvas.delete("wire")
        for index, tab in enumerate(self.tabs):
            if index not in self._filesview_boxes:
                continue
            for target_index in tab.get("file_references", []):
                if target_index not in self._filesview_boxes:
                    continue
                self._draw_one_file_wire(index, target_index)

    def _draw_one_file_wire(self, source_index, target_index):
        _, src_widget = self._filesview_boxes[source_index]
        _, dst_widget = self._filesview_boxes[target_index]
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        dh = dst_widget.winfo_height() or 70
        src_tab = self.tabs[source_index]
        dst_tab = self.tabs[target_index]

        x0 = src_tab["canvas_x"] + sw
        y0 = src_tab["canvas_y"] + sh / 2
        x1 = dst_tab["canvas_x"]
        y1 = dst_tab["canvas_y"] + dh / 2

        pull = max(abs(x1 - x0) * 0.5, 40)
        p0 = (x0, y0)
        p1 = (x0 + pull, y0)
        p2 = (x1 - pull, y1)
        p3 = (x1, y1)

        tag = f"file_wire_{source_index}_{target_index}"
        self.workspace_canvas.create_line(
            *self._bezier_points(p0, p1, p2, p3), smooth=True,
            fill="#4a90d9", width=2, tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.create_oval(
            x1 - 4, y1 - 4, x1 + 4, y1 + 4, fill="#4a90d9", outline="",
            tags=("fileview", "wire", tag)
        )

    def render_file_view(self):
        """Phase C2: freeform ComfyUI-style canvas. Node boxes sit at
        explicit, draggable (canvas_x, canvas_y) positions and are
        drawn directly on workspace_canvas (via create_window) rather
        than pack()-stacked into workspace_frame, so they can be placed
        anywhere. Curved wires are drawn between them from the derived
        `references` graph (see recompute_references/draw_wires) -
        double-clicking a wire removes the func_call block that
        produced it. Shows whichever level of the hierarchy
        file_view_path points at (top-level nodes, or a class's
        child_nodes). Double-click a box (or its Open button) enters
        that node via open_node()."""
        tab = self.tabs[self.active_tab_index]
        normalize_orders(tab["nodes"])
        nodes = self.get_current_node_list(tab)

        self._fileview_boxes = {}
        # Defensive: a refresh mid wire-drag (e.g. triggered by something
        # else while dragging) would otherwise leave a dangling temp line
        # and stale hover state pointing at boxes that are about to be
        # destroyed and recreated.
        self.workspace_canvas.delete("wire_drag_temp")
        self._wire_drag_source = None
        self._wire_drag_temp_id = None
        self._wire_drag_hover_id = None

        if not nodes:
            self.show_empty_state()
            return

        self.assign_default_canvas_positions(nodes)

        for node in nodes:
            self.create_fileview_node_box(node)

        self.workspace_frame.update_idletasks()
        self.draw_wires()
        self._update_fileview_scrollregion()

    def assign_default_canvas_positions(self, nodes):
        """Give any node without a stored canvas position a sensible
        default grid slot (3 per row) so a freshly created node - or a
        file that predates C2 entirely - always has somewhere valid to
        render. Positions aren't a real persistence format yet (see
        carry-forward item 4 in the handoff) - they just live on the
        in-memory node dict like everything else in Phase B/C. Never
        overwrites a position the user has already dragged a node to."""
        col_width, row_height = 260, 150
        start_x, start_y = 30, 20
        per_row = 3
        idx = 0
        for node in nodes:
            if "canvas_x" not in node or "canvas_y" not in node:
                row, col = divmod(idx, per_row)
                node["canvas_x"] = start_x + col * col_width
                node["canvas_y"] = start_y + row * row_height
            idx += 1

    def create_fileview_node_box(self, node):
        """Build one node's draggable box and place it on
        workspace_canvas at its stored position. Visually identical to
        the pre-C2 B2/B3 box (same icon/lock/color scheme) - only how
        it's placed and how it responds to the mouse has changed.

        Phase D: a third kind, "category", joins "function"/"class" -
        a pure visual folder (zero codegen effect, unlike class) that
        can hold anything, styled distinctly (folder icon, gold) so
        it's never mistaken for a class node at a glance."""
        kind = node.get("kind", "function")
        is_class = kind == "class"
        is_category = kind == "category"
        is_container = is_class or is_category
        if is_category:
            box_color = "#8a6a2a"
        elif is_class:
            box_color = "#5a4a8a"
        else:
            box_color = CATEGORY_COLORS.get("Basic", "#4a4a4a")
        text_fg = "#ffffff" if is_container else "#000000"
        box = tk.Frame(
            self.workspace_canvas, bg=BLOCK_BG, highlightthickness=2,
            highlightbackground=DARK_BORDER
        )

        def _open(_e=None, nid=node["id"]):
            self.open_node(nid)

        if is_category:
            icon = "\U0001F4C1"  # folder
        elif is_class:
            icon = "\U0001F3DB"  # classical building
        else:
            icon = "\U0001F9E9"  # puzzle piece
        header = tk.Frame(box, bg=box_color, width=215, height=36, cursor="fleur")
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        name_label = tk.Label(
            header, text=f"{icon} {node['name']}",
            bg=box_color, fg=text_fg,
            font=("Segoe UI", 10, "bold"), anchor="w", cursor="fleur"
        )
        name_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        # Execution order badge (function nodes only): "#N" is this
        # node's place in the generated file; "#?" + a red outline
        # means it's unassigned and must be given a number. Click to
        # change it (locked nodes' badges are fixed).
        if not is_container:
            order_val = node.get("order")
            unassigned = "order" in node and order_val is None
            badge = tk.Label(
                header, text="#?" if unassigned else f"#{order_val}",
                bg="#c62828" if unassigned else box_color,
                fg="#ffffff" if unassigned else text_fg,
                font=("Segoe UI", 10, "bold"),
                cursor="arrow" if node.get("locked") else "hand2")
            badge.pack(side=tk.LEFT, padx=(8, 0))
            if not node.get("locked"):
                badge.bind("<Button-1>",
                           lambda e, nid=node["id"]: self.set_node_order_dialog(nid))
            if unassigned:
                box.configure(highlightbackground="#ff3b3b")

        # Phase C3: an output "port" handle, only on function-kind nodes
        # in a language that actually has a func_call block (HTML has
        # none, so wiring makes no sense there). Neither class nor
        # category nodes wire directly - they hold other nodes, not
        # blocks. Dragging from this handle to another node's box calls
        # that node - see _port_press/_port_motion/_port_release below.
        can_wire = (not is_container) and "func_call" in self.blocks
        port = None
        if can_wire:
            port = tk.Label(
                header, text="\u25cf", bg=box_color, fg=text_fg,
                font=("Segoe UI", 12, "bold"), cursor="crosshair"
            )
            port.pack(side=tk.RIGHT, padx=(4, 8))

        if node.get("locked"):
            tk.Label(
                header, text="\U0001F512", bg=box_color, fg=text_fg,
            ).pack(side=tk.RIGHT, padx=8)

        # Re-pack the name last so the badge, lock and port get their
        # full width first (the header has a fixed width, so a short
        # box would otherwise squeeze them out).
        name_label.pack_forget()
        name_label.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        body = tk.Frame(box, bg=BLOCK_BG)
        body.pack(fill=tk.X, padx=10, pady=8)
        if is_container:
            count = len(node.get("child_nodes", []))
            label_text = f"{count} node{'s' if count != 1 else ''} inside"
        else:
            count = len(node["blocks"])
            label_text = f"{count} block{'s' if count != 1 else ''}"
        tk.Label(
            body, text=label_text,
            bg=BLOCK_BG, fg="#888888", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT)
        tk.Button(
            body, text="Open \u2192", bg="#3a3a3a", fg=DARK_FG,
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
            command=_open
        ).pack(side=tk.RIGHT)

        win_id = self.workspace_canvas.create_window(
            node["canvas_x"], node["canvas_y"], anchor="nw", window=box,
            tags=("fileview", "node_box")
        )
        self._fileview_boxes[node["id"]] = (win_id, box)
        self._bind_context_recursive(
            box, lambda e, nid=node["id"]: self._on_node_box_right_click(e, nid))

        # Dragging is grabbed from the header only, so the Open button
        # and double-click-to-open both keep working undisturbed. A
        # small movement threshold distinguishes an actual drag from a
        # click/double-click, since a plain click never moves the
        # mouse far enough to cross it.
        drag_state = {"dragging": False, "start_x": 0, "start_y": 0,
                      "node_x0": 0, "node_y0": 0}

        def _press(e, nid=node["id"]):
            drag_state["dragging"] = False
            drag_state["start_x"] = e.x_root
            drag_state["start_y"] = e.y_root
            n = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], nid)
            if n is None:
                return
            drag_state["node_x0"] = n["canvas_x"]
            drag_state["node_y0"] = n["canvas_y"]

        def _motion(e, nid=node["id"]):
            dx = e.x_root - drag_state["start_x"]
            dy = e.y_root - drag_state["start_y"]
            if not drag_state["dragging"] and (abs(dx) > 4 or abs(dy) > 4):
                drag_state["dragging"] = True
            if not drag_state["dragging"]:
                return
            n = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], nid)
            if n is None:
                return
            new_x = drag_state["node_x0"] + dx
            new_y = drag_state["node_y0"] + dy
            n["canvas_x"], n["canvas_y"] = new_x, new_y
            wid, _ = self._fileview_boxes.get(nid, (None, None))
            if wid is not None:
                self.workspace_canvas.coords(wid, new_x, new_y)
            self.draw_wires_for(nid)

        def _release(e, nid=node["id"]):
            if drag_state["dragging"]:
                self.mark_active_tab_dirty()
                self._update_fileview_scrollregion()
            drag_state["dragging"] = False

        for w in (header, name_label):
            w.bind("<ButtonPress-1>", _press)
            w.bind("<B1-Motion>", _motion)
            w.bind("<ButtonRelease-1>", _release)
            w.bind("<Double-Button-1>", _open)

        if port is not None:
            port.bind("<ButtonPress-1>", lambda e, nid=node["id"]: self._port_press(e, nid))
            port.bind("<B1-Motion>", self._port_motion)
            port.bind("<ButtonRelease-1>", self._port_release)

    def _canvas_coords_from_event(self, e):
        """Convert a mouse event fired on some widget nested inside
        workspace_canvas (a port label several frames deep) into actual
        canvas coordinates, accounting for scroll offset. canvasx/canvasy
        expect a position relative to the canvas widget itself, not the
        screen, so root coordinates are translated through the canvas's
        own screen origin first."""
        rel_x = e.x_root - self.workspace_canvas.winfo_rootx()
        rel_y = e.y_root - self.workspace_canvas.winfo_rooty()
        return self.workspace_canvas.canvasx(rel_x), self.workspace_canvas.canvasy(rel_y)

    def _port_press(self, e, source_id):
        """Phase C3: start dragging a wire from source_id's output port.
        Draws a temporary dashed line that follows the mouse until
        release; the real wire only gets created (as a func_call block
        inserted into the source node) if release lands on a valid
        target box - see _port_release."""
        tab = self.tabs[self.active_tab_index]
        src_node = find_node_by_id(tab["nodes"], source_id)
        wid_pair = self._fileview_boxes.get(source_id)
        if src_node is None or wid_pair is None:
            return
        _, src_widget = wid_pair
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        x0 = src_node["canvas_x"] + sw
        y0 = src_node["canvas_y"] + sh / 2

        self._wire_drag_source = source_id
        self._wire_drag_start = (x0, y0)
        self._wire_drag_temp_id = self.workspace_canvas.create_line(
            x0, y0, x0, y0, fill="#e8a33d", width=2, dash=(5, 3),
            tags=("wire_drag_temp",)
        )

    def _port_motion(self, e):
        """Redraw the in-progress wire-drag line to follow the mouse,
        and highlight whichever node box (if any) the cursor is
        currently over, so it's clear where releasing would connect
        to. Purely visual - no data changes until _port_release."""
        if self._wire_drag_source is None or self._wire_drag_temp_id is None:
            return
        cx, cy = self._canvas_coords_from_event(e)
        x0, y0 = self._wire_drag_start
        self.workspace_canvas.coords(self._wire_drag_temp_id, x0, y0, cx, cy)

        target_id = self._node_box_at(cx, cy, exclude_id=self._wire_drag_source)
        if target_id != self._wire_drag_hover_id:
            if self._wire_drag_hover_id is not None:
                prev = self._fileview_boxes.get(self._wire_drag_hover_id)
                if prev is not None:
                    prev[1].configure(highlightbackground=DARK_BORDER)
            if target_id is not None:
                cur = self._fileview_boxes.get(target_id)
                if cur is not None:
                    cur[1].configure(highlightbackground="#e8a33d")
            self._wire_drag_hover_id = target_id

    def _port_release(self, e):
        """Finish a wire-drag: if the mouse was released on top of a
        valid, different function-kind node's box, insert a func_call
        block (targeting that node's name) into the source node's
        top-level blocks - the same underlying data change a user
        adding that block by hand through the palette would produce.
        Always cleans up the temp line/hover highlight regardless of
        whether a connection was actually made."""
        source_id = self._wire_drag_source
        cx, cy = self._canvas_coords_from_event(e) if source_id is not None else (0, 0)

        if self._wire_drag_temp_id is not None:
            self.workspace_canvas.delete(self._wire_drag_temp_id)
            self._wire_drag_temp_id = None
        if self._wire_drag_hover_id is not None:
            hovered = self._fileview_boxes.get(self._wire_drag_hover_id)
            if hovered is not None:
                hovered[1].configure(highlightbackground=DARK_BORDER)
            self._wire_drag_hover_id = None

        target_id = self._node_box_at(cx, cy, exclude_id=source_id) if source_id is not None else None
        self._wire_drag_source = None
        if target_id is not None:
            self.add_wire_by_drag(source_id, target_id)

    def _node_box_at(self, cx, cy, exclude_id=None):
        """Return the id of whichever currently-drawn function-kind node
        box contains canvas point (cx, cy), or None. Used both to
        highlight a hover target mid-drag and to resolve the actual
        drop target on release, so the two always agree on hit-testing."""
        tab = self.tabs[self.active_tab_index]
        for node in self.get_current_node_list(tab):
            if node["id"] == exclude_id:
                continue
            if node.get("kind", "function") != "function":
                continue
            wid_pair = self._fileview_boxes.get(node["id"])
            if wid_pair is None:
                continue
            _, widget = wid_pair
            nx, ny = node["canvas_x"], node["canvas_y"]
            nw = widget.winfo_width() or 220
            nh = widget.winfo_height() or 70
            if nx <= cx <= nx + nw and ny <= cy <= ny + nh:
                return node["id"]
        return None

    def add_wire_by_drag(self, source_id, target_id):
        """Insert a func_call block (targeting target_id's node name)
        into source_id's top-level blocks. This is the one place a
        wire gets created by drawing rather than by hand-adding a
        func_call block through the palette - everything downstream
        (references, the drawn wire itself) is still fully derived,
        same as ever, so nothing else needs to know a drag caused it."""
        tab = self.tabs[self.active_tab_index]
        source = find_node_by_id(tab["nodes"], source_id)
        target = find_node_by_id(tab["nodes"], target_id)
        if source is None or target is None:
            return
        source["blocks"].append(("func_call", {"name": target["name"], "args": ""}))
        self.mark_active_tab_dirty()
        self.refresh_workspace()

    def draw_wires(self):
        """Redraw every wire (a derived call-graph edge between two
        function nodes) as a curved connector on workspace_canvas.
        Pure rendering of node['references'] - never mutates it, and
        only draws an edge when both endpoints are boxes actually shown
        at the current file-view depth (a class's internal nodes don't
        draw wires out to their siblings' external callers, etc.).
        Called after every file-view refresh and on every drag motion,
        so wires always track the boxes they connect live."""
        self.workspace_canvas.delete("wire")
        tab = self.tabs[self.active_tab_index]
        nodes_shown = self.get_current_node_list(tab)
        shown_ids = {n["id"] for n in nodes_shown}

        for node in nodes_shown:
            if node.get("kind", "function") != "function":
                continue
            if node["id"] not in self._fileview_boxes:
                continue
            for target_id in node.get("references", []):
                if target_id not in shown_ids or target_id not in self._fileview_boxes:
                    continue
                self._draw_one_wire(node["id"], target_id)

    def draw_wires_for(self, node_id):
        """Redraw only the wires touching `node_id` (drag-motion fast path).
        Same edge rules as draw_wires(); every other wire is left as is, so
        a drag costs O(that node's edges) instead of O(all edges)."""
        tab = self.tabs[self.active_tab_index]
        nodes_shown = self.get_current_node_list(tab)
        shown_ids = {n["id"] for n in nodes_shown}
        if node_id not in shown_ids or node_id not in self._fileview_boxes:
            self.draw_wires()
            return
        edges = []
        for node in nodes_shown:
            if node.get("kind", "function") != "function" or node["id"] not in self._fileview_boxes:
                continue
            for target_id in node.get("references", []):
                if target_id not in shown_ids or target_id not in self._fileview_boxes:
                    continue
                if node["id"] == node_id or target_id == node_id:
                    edges.append((node["id"], target_id))
        for source_id, target_id in edges:
            self.workspace_canvas.delete(f"wire_{source_id}_{target_id}")
        for source_id, target_id in edges:
            self._draw_one_wire(source_id, target_id)

    def _draw_one_wire(self, source_id, target_id):
        _, src_widget = self._fileview_boxes[source_id]
        _, dst_widget = self._fileview_boxes[target_id]
        sw = src_widget.winfo_width() or 220
        sh = src_widget.winfo_height() or 70
        dh = dst_widget.winfo_height() or 70
        tab = self.tabs[self.active_tab_index]
        src_node = find_node_by_id(tab["nodes"], source_id)
        dst_node = find_node_by_id(tab["nodes"], target_id)
        if not src_node or not dst_node:
            return
        x0 = src_node["canvas_x"] + sw
        y0 = src_node["canvas_y"] + sh / 2
        x1 = dst_node["canvas_x"]
        y1 = dst_node["canvas_y"] + dh / 2

        # ComfyUI-style cubic bezier: control points pulled
        # horizontally outward from each endpoint, so the curve leaves
        # and arrives roughly perpendicular to the box edge no matter
        # the relative position of the two boxes (including one
        # stacked directly above/below the other).
        pull = max(abs(x1 - x0) * 0.5, 40)
        p0 = (x0, y0)
        p1 = (x0 + pull, y0)
        p2 = (x1 - pull, y1)
        p3 = (x1, y1)

        tag = f"wire_{source_id}_{target_id}"
        selected = self._fileview_selected_wire == (source_id, target_id)
        color = "#e8a33d" if selected else "#6a9955"
        width = 3 if selected else 2
        self.workspace_canvas.create_line(
            *self._bezier_points(p0, p1, p2, p3), smooth=True,
            fill=color, width=width, tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.create_oval(
            x1 - 4, y1 - 4, x1 + 4, y1 + 4, fill=color, outline="",
            tags=("fileview", "wire", tag)
        )
        self.workspace_canvas.tag_bind(
            tag, "<Button-1>",
            lambda e, s=source_id, t=target_id: self.select_wire(s, t)
        )
        self.workspace_canvas.tag_bind(
            tag, "<Double-Button-1>",
            lambda e, s=source_id, t=target_id: self.delete_wire(s, t)
        )

    def _bezier_points(self, p0, p1, p2, p3, segments=24):
        """Flatten a cubic bezier into a polyline for Canvas's own
        smooth=True line drawing (Tkinter has no native bezier item)."""
        pts = []
        for i in range(segments + 1):
            t = i / segments
            mt = 1 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
            pts.extend([x, y])
        return pts

    def select_wire(self, source_id, target_id):
        """Single-click a wire to highlight it (orange, thicker) -
        purely visual feedback that a specific call edge is what a
        follow-up double-click would delete."""
        self._fileview_selected_wire = (source_id, target_id)
        self.draw_wires()

    def delete_wire(self, source_id, target_id):
        """Double-clicking a drawn wire removes the underlying
        func_call block from the source node - never the reverse (the
        wire itself is never hand-editable, only what produces it is).
        If the source calls the target more than once, this removes
        just the first matching func_call found; the wire stays drawn
        until every call to that target is gone, matching one
        double-click removing one edge's worth of calls at a time."""
        tab = self.tabs[self.active_tab_index]
        source = find_node_by_id(tab["nodes"], source_id)
        target = find_node_by_id(tab["nodes"], target_id)
        if not source or not target:
            return
        removed = self.remove_first_func_call_targeting(source["blocks"], target["name"])
        if removed:
            self._fileview_selected_wire = None
            self.mark_active_tab_dirty()
            self.refresh_workspace()

    def remove_first_func_call_targeting(self, block_list, target_name):
        """Recursively find and remove the first func_call block (at
        any nesting depth, including inside a container block's
        _children) whose name matches target_name. Returns True if
        something was removed. Mirrors iter_all_blocks_recursive's
        traversal order so "first" is well-defined and matches what a
        user would read top-to-bottom in the block editor."""
        for i, (block_id, params) in enumerate(block_list):
            if block_id == "func_call" and (params.get("name") or "").strip() == target_name:
                del block_list[i]
                return True
        for block_id, params in block_list:
            module = self.blocks.get(block_id)
            if module and get_block_attr(module, "is_container", False):
                if self.remove_first_func_call_targeting(params.get("_children", []), target_name):
                    return True
        return False

    def _update_fileview_scrollregion(self):
        """Size workspace_canvas's scrollregion to whatever the
        freeform boxes/wires currently occupy, so dragging a node far
        out lets the existing scrollbar reach it instead of clipping
        it. Pan/zoom proper is deferred (see handoff carry-forward
        item 1) - this first pass reuses the plain vertical/horizontal
        scrollbar machinery already in place for the block editor."""
        bbox = self.workspace_canvas.bbox("fileview")
        if bbox:
            x0, y0, x1, y1 = bbox
            self.workspace_canvas.configure(scrollregion=(0, 0, x1 + 60, y1 + 60))
        else:
            self.workspace_canvas.configure(scrollregion=self.workspace_canvas.bbox("all"))

    def assign_default_tab_canvas_positions(self):
        """Files-layer equivalent of assign_default_canvas_positions():
        give any tab without a stored canvas position a sensible
        default grid slot (3 per row), never overwriting a position
        the user has already dragged a file box to."""
        col_width, row_height = 260, 150
        start_x, start_y = 30, 20
        per_row = 3
        for idx, tab in enumerate(self.tabs):
            if "canvas_x" not in tab or "canvas_y" not in tab:
                row, col = divmod(idx, per_row)
                tab["canvas_x"] = start_x + col * col_width
                tab["canvas_y"] = start_y + row * row_height
