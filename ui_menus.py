"""Right-click context menus."""
import tkinter as tk
import sys
from nodes_model import find_node_by_id
from ui_common import CATEGORY_COLORS, DARK_FG, DARK_HOVER, DARK_PANEL, get_block_attr


class MenusMixin:

    # ------------------------------------------------------------------
    # Workspace right-click menu (ComfyUI-style): top entry adds
    # something appropriate to the current layer, below it a Panels
    # submenu shows/hides parts of the window.
    # ------------------------------------------------------------------

    def _bind_workspace_context_menu(self):
        """Right-click on EMPTY workspace area (canvas or the block-editor
        frame). Node/file boxes and blocks are child widgets, so a click on
        them never reaches these bindings."""
        if sys.platform == "darwin":
            seqs = ("<Button-2>", "<Control-Button-1>")
        else:
            seqs = ("<Button-3>",)
        for w in (self.workspace_canvas, self.workspace_frame):
            for seq in seqs:
                w.bind(seq, self._on_workspace_right_click)

    def _on_workspace_right_click(self, event):
        gid = self._group_title_at(event) if self.canvas_layer_active() else None
        if gid:
            self.popup_menu(self.build_group_menu(gid), event.x_root, event.y_root)
            return
        x, y = self._canvas_coords_from_event(event)
        self.popup_menu(self.build_workspace_menu((max(0, x), max(0, y))), event.x_root, event.y_root)

    def _new_menu(self, parent):
        return tk.Menu(parent, tearoff=0, bg=DARK_PANEL, fg=DARK_FG,
                       activebackground=DARK_HOVER, activeforeground=DARK_FG)

    def build_workspace_menu(self, canvas_pos):
        """Build (don't show) the right-click menu for the current layer.
        canvas_pos is where the click landed, in canvas coordinates, used
        to place new nodes/categories/files under the cursor."""
        menu = self._new_menu(self)
        menu._vars = []  # keep BooleanVars alive for the checkbuttons

        in_code_view = (
            (self.view_mode == "file" and self.file_view_code_mode)
            or (self.view_mode == "files" and self.files_view_code_mode)
        )
        added = False
        if not in_code_view:
            if self.view_mode == "node":
                self._add_block_cascade(menu)
                added = True
            elif self.view_mode == "file":
                menu.add_command(label="\u2795 Add node",
                                 command=lambda: self.create_node(pos=canvas_pos))
                menu.add_command(label="\U0001F4C1 Add category",
                                 command=lambda: self.create_category(pos=canvas_pos))
                menu.add_command(label="\u25ad Add group",
                                 command=lambda: self.add_group(canvas_pos))
                self.add_template_cascades(
                    menu, lambda e: self.insert_node_template(e, canvas_pos), separator=True)
                added = True
            elif self.view_mode == "files":
                menu.add_command(label="\u2795 New file",
                                 command=lambda: self.create_file_at(canvas_pos))
                menu.add_command(label="\u25ad Add group",
                                 command=lambda: self.add_group(canvas_pos))
                added = True
        if added:
            menu.add_separator()

        panels = self._new_menu(menu)
        v = tk.BooleanVar(value=self.panels.is_visible("palette"))
        menu._vars.append(v)
        panels.add_checkbutton(label="Block Palette", variable=v,
                               command=self.toggle_palette)
        if self.view_mode == "node":  # the code panel only exists at Blocks layer
            v2 = tk.BooleanVar(value=self.panels.is_visible("code"))
            menu._vars.append(v2)
            panels.add_checkbutton(label="Generated Code", variable=v2,
                                   command=self.toggle_code_panel)
        menu.add_cascade(label="\u25a4 Panels", menu=panels)
        return menu

    def build_drop_menu(self, source_id, pos):
        """Menu shown when a wire is dropped on empty canvas: New node at
        the top, ready-made starter nodes below."""
        menu = self._new_menu(self)
        menu.add_command(label="\u2795 New node",
                         command=lambda: self._drop_new_node(source_id, pos))
        menu.add_separator()
        for key, label in self.STARTER_NODES:
            menu.add_command(
                label=label,
                command=lambda k=key: self.create_starter_node(k, pos, wire_from=source_id))
        self.add_template_cascades(
            menu, lambda e: self.insert_node_template(e, pos, wire_from=source_id), separator=True)
        return menu

    def _drop_new_node(self, source_id, pos):
        """Named new node (asks for the name), wired from the source."""
        before = {n["id"] for n in self.get_current_node_list(self.tabs[self.active_tab_index])}
        self.create_node(pos=pos)
        for n in self.get_current_node_list(self.tabs[self.active_tab_index]):
            if n["id"] not in before and n.get("kind", "function") == "function":
                self.add_wire_by_drag(source_id, n["id"])

    def show_drop_menu(self, source_id, pos, x_root, y_root):
        menu = self.build_drop_menu(source_id, pos)
        self._dismiss_popup()
        self._install_popup_guards()
        self._drop_menu = menu

        def close(_e=None):
            self._dismiss_drop_menu()
        menu.bind("<Escape>", close)
        try:
            menu.tk_popup(int(x_root), int(y_root))
        finally:
            menu.grab_release()

    def _dismiss_drop_menu(self):
        menu = getattr(self, "_drop_menu", None)
        if menu is not None:
            try:
                menu.unpost()
            except tk.TclError:
                pass
            self._drop_menu = None

    def _add_block_cascade(self, menu):
        """'Add block' > category > block, same source/order as the palette."""
        sub = self._new_menu(menu)
        any_block = False
        for category in self.get_ordered_categories():
            blocks = self.blocks_by_category.get(category) or []
            if not blocks:
                continue
            any_block = True
            cat_menu = self._new_menu(sub)
            for b in blocks:
                cat_menu.add_command(
                    label=get_block_attr(b, "display_name", "Unknown"),
                    command=lambda b=b: self.add_block_to_workspace(b))
            sub.add_cascade(label=category, menu=cat_menu,
                            foreground=CATEGORY_COLORS.get(category, DARK_FG))
        menu.add_cascade(label="\u2795 Add block", menu=sub,
                         state=tk.NORMAL if any_block else tk.DISABLED)

    # --- box menus ---

    def _context_seqs(self):
        return ("<Button-2>", "<Control-Button-1>") if sys.platform == "darwin" else ("<Button-3>",)

    def _bind_context_recursive(self, widget, handler):
        for seq in self._context_seqs():
            widget.bind(seq, handler)
        for child in widget.winfo_children():
            self._bind_context_recursive(child, handler)

    def _popup(self, menu, event):
        self.popup_menu(menu, event.x_root, event.y_root)
        return "break"

    # ---- popup lifetime: a posted menu must never outlive its moment -----
    def popup_menu(self, menu, x_root, y_root):
        """Post a right-click menu and remember it, so it can be closed by
        Escape, a click elsewhere, minimizing/moving the window or the
        window losing focus (Tk menus on some Linux desktops otherwise
        stay on screen until clicked, even over other apps)."""
        self._dismiss_popup()
        self._active_popup = menu
        self._install_popup_guards()
        try:
            menu.tk_popup(int(x_root), int(y_root))
        finally:
            menu.grab_release()

    def _install_popup_guards(self):
        if getattr(self, "_popup_guards_installed", False):
            return
        self._popup_guards_installed = True
        top = self.winfo_toplevel()
        for seq in ("<Unmap>", "<Configure>"):
            top.bind(seq, lambda e: e.widget is top and self._dismiss_popup(), add="+")
        top.bind("<Escape>", lambda e: self._dismiss_popup(), add="+")
        top.bind("<FocusOut>", self._popup_focus_out, add="+")

    def _popup_focus_out(self, e):
        if e.widget is self.winfo_toplevel():
            self.after(150, self._dismiss_popup_if_unfocused)

    def _dismiss_popup_if_unfocused(self):
        try:
            if self.focus_displayof() is None:
                self._dismiss_popup()
        except tk.TclError:
            pass

    def _dismiss_popup(self, _e=None):
        menu = getattr(self, "_active_popup", None)
        self._active_popup = None
        if menu is not None:
            try:
                menu.unpost()
            except tk.TclError:
                pass
        self._dismiss_drop_menu()

    # ---- multi-selection (Shift+right-click) ---------------------------
    def selected_nodes(self):
        return self.__dict__.setdefault("_selected_node_ids", set())

    def _paint_node_selection(self, node_id):
        entry = getattr(self, "_fileview_boxes", {}).get(node_id)
        if not entry:
            return
        from ui_common import DARK_BORDER
        from ui_canvas import SELECT_COLOR
        node = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], node_id)
        if node_id in self.selected_nodes():
            color = SELECT_COLOR
        elif node is not None and "order" in node and node["order"] is None \
                and node.get("kind", "function") == "function":
            color = "#ff3b3b"
        else:
            color = DARK_BORDER
        try:
            entry[1].configure(highlightbackground=color)
        except tk.TclError:
            pass

    # ---- single selection of a file box / a block (cyan outline) ---------
    def select_file_box(self, index):
        old = getattr(self, "_selected_file_index", None)
        self._selected_file_index = index
        from ui_common import DARK_BORDER
        from ui_canvas import SELECT_COLOR
        boxes = getattr(self, "_filesview_boxes", {})
        for i, color in ((old, DARK_BORDER), (index, SELECT_COLOR)):
            entry = boxes.get(i)
            if entry:
                try:
                    entry[1].configure(highlightbackground=color)
                except tk.TclError:
                    pass

    def is_block_selected(self, index, container_list):
        return (container_list is getattr(self, "_selected_block_list", None)
                and index == getattr(self, "_selected_block_index", None))

    def select_block(self, index, container_list):
        self._selected_block_list = container_list
        self._selected_block_index = index
        self._repaint_block_selection()

    def _repaint_block_selection(self):
        from ui_widgets import BlockWidget

        def walk(w):
            for child in w.winfo_children():
                if isinstance(child, BlockWidget):
                    child.refresh_selection_border()
                walk(child)
        try:
            walk(self.workspace_frame)
        except (tk.TclError, AttributeError):
            pass

    def toggle_node_selected(self, node_id):
        sel = self.selected_nodes()
        sel.symmetric_difference_update({node_id})
        self._paint_node_selection(node_id)
        self._refresh_nav_for_selection()

    def clear_node_selection(self):
        old = list(self.selected_nodes())
        self.selected_nodes().clear()
        for nid in old:
            self._paint_node_selection(nid)
        if old:
            self._refresh_nav_for_selection()

    def _refresh_nav_for_selection(self):
        """The nav bar offers "Open N selected together" - keep it in step."""
        if self.view_mode == "file" and not self.file_view_code_mode:
            self.refresh_node_nav()

    def toggle_ignore_node(self, node_id):
        """Right-click > Ignore: the node stays in the project but is left
        out of generated code. Applies to every selected node when the
        clicked one is part of a multi-selection."""
        tab = self.tabs[self.active_tab_index]
        sel = self.selected_nodes()
        ids = list(sel) if node_id in sel and len(sel) > 1 else [node_id]
        nodes = [n for n in (find_node_by_id(tab["nodes"], i) for i in ids)
                 if n is not None and n.get("kind", "function") == "function"]
        if not nodes:
            return
        make_ignored = not all(n.get("ignored") for n in nodes)
        for n in nodes:
            if make_ignored:
                n["ignored"] = True
                n.pop("skipped", None)
            else:
                n.pop("ignored", None)
        self.mark_active_tab_dirty()
        self.refresh_workspace()

    def toggle_skip_node(self, node_id):
        """Right-click > Skip (purple): bypass - the node is left out of the
        generated code AND so is every call to it, so the program still runs
        without it. Skip and Ignore exclude each other. Applies to every
        selected node when the clicked one is part of a multi-selection."""
        tab = self.tabs[self.active_tab_index]
        sel = self.selected_nodes()
        ids = list(sel) if node_id in sel and len(sel) > 1 else [node_id]
        nodes = [n for n in (find_node_by_id(tab["nodes"], i) for i in ids)
                 if n is not None and n.get("kind", "function") == "function"]
        if not nodes:
            return
        make_skipped = not all(n.get("skipped") for n in nodes)
        for n in nodes:
            if make_skipped:
                n["skipped"] = True
                n.pop("ignored", None)
            else:
                n.pop("skipped", None)
        self.mark_active_tab_dirty()
        self.refresh_workspace()

    def build_node_menu(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        menu = self._new_menu(self)
        if node is None:
            return menu
        locked = bool(node.get("locked"))
        off = tk.DISABLED if locked else tk.NORMAL
        menu.add_command(label="Open", command=lambda: self.open_node(node_id))
        if node_id in self.selected_nodes() and len(self.selected_function_nodes()) >= 2:
            menu.add_command(label=self.open_together_label(),
                             command=self.open_selected_nodes)
        if node_id in self.selected_nodes() and len(self.selected_nodes()) >= 2:
            menu.add_command(label=self.group_selected_label(),
                             command=self.group_selected_nodes)
        if node.get("kind", "function") == "function":
            sel = self.selected_nodes()
            multi = node_id in sel and len(sel) > 1
            all_ign = bool(node.get("ignored")) if not multi else all(
                (find_node_by_id(tab["nodes"], i) or {}).get("ignored") for i in sel)
            menu.add_command(
                label=("Stop ignoring" if all_ign else "Ignore") + (f" ({len(sel)} selected)" if multi else ""),
                command=lambda: self.toggle_ignore_node(node_id))
            all_skip = bool(node.get("skipped")) if not multi else all(
                (find_node_by_id(tab["nodes"], i) or {}).get("skipped") for i in sel)
            menu.add_command(
                label=("Stop skipping" if all_skip else "Skip") + (f" ({len(sel)} selected)" if multi else ""),
                command=lambda: self.toggle_skip_node(node_id))
        menu.add_command(label="Rename\u2026", state=off,
                         command=lambda: self.rename_node_dialog(node_id))
        if node.get("kind", "function") == "function":
            menu.add_command(label="Set order\u2026", state=off,
                             command=lambda: self.set_node_order_dialog(node_id))
        if node.get("kind", "function") in ("function", "class"):
            menu.add_command(label="Save as node template\u2026",
                             command=lambda: self.save_node_as_template_dialog(node_id))
        dests = self.move_destinations(tab, node)
        move = self._new_menu(menu)
        for label, lst in dests:
            move.add_command(label=label,
                             command=lambda lst=lst: self.move_node(tab, node, lst))
        menu.add_cascade(label="Move to", menu=move,
                         state=tk.NORMAL if dests else tk.DISABLED)
        menu.add_separator()
        menu.add_command(label="Delete\u2026", state=off,
                         command=lambda: self.delete_node_dialog(node_id))
        return menu

    def build_file_menu(self, index):
        menu = self._new_menu(self)
        menu.add_command(label="Open", command=lambda: self.open_file_from_files_view(index))
        menu.add_command(label="Rename\u2026", command=lambda: self.rename_file_dialog(index))
        menu.add_separator()
        menu.add_command(label="Close file", command=lambda: self.close_file_from_files_view(index))
        return menu

    def _on_node_box_right_click(self, event, node_id):
        if getattr(event, "state", 0) & 0x0001:       # Shift+right-click = select
            self._dismiss_popup()
            self.toggle_node_selected(node_id)
            return "break"
        return self._popup(self.build_node_menu(node_id), event)

    def _on_file_box_right_click(self, event, index):
        return self._popup(self.build_file_menu(index), event)
