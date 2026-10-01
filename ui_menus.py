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
        x, y = self._canvas_coords_from_event(event)
        menu = self.build_workspace_menu((max(0, x), max(0, y)))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

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
                added = True
            elif self.view_mode == "files":
                menu.add_command(label="\u2795 New file",
                                 command=lambda: self.create_file_at(canvas_pos))
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
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def build_node_menu(self, node_id):
        tab = self.tabs[self.active_tab_index]
        node = find_node_by_id(tab["nodes"], node_id)
        menu = self._new_menu(self)
        if node is None:
            return menu
        locked = bool(node.get("locked"))
        off = tk.DISABLED if locked else tk.NORMAL
        menu.add_command(label="Open", command=lambda: self.open_node(node_id))
        menu.add_command(label="Rename\u2026", state=off,
                         command=lambda: self.rename_node_dialog(node_id))
        if node.get("kind", "function") == "function":
            menu.add_command(label="Set order\u2026", state=off,
                             command=lambda: self.set_node_order_dialog(node_id))
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
        return self._popup(self.build_node_menu(node_id), event)

    def _on_file_box_right_click(self, event, index):
        return self._popup(self.build_file_menu(index), event)
