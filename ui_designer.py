"""The UI designer inside the app: finds out when an attached UI node should show
the designer, registers it as an editor, and takes a node back from code-only.
The designer itself is designer_editor.UIDesignerEditor."""
import tkinter as tk
from tkinter import messagebox

import ui_node
import ui_parse
from codebuilder_api import CodeBuilderFacade
import doc_types
from designer_editor import UIDesignerEditor
from designer_port import CodeBuilderUIPort
from editor_host import AppEditorHost
from editors import EditorSpec
from nodes_model import find_node_by_id
from ui_common import DARK_ACCENT, DARK_BG, DARK_FG
from ui_widgets import EventRowWidget


DESIGNER_SPEC = EditorSpec("ui-designer", "UI designer", doc_types.CODEBUILDER, "ui-node",
                           lambda app: app.designer_editor)


class DesignerMixin:

    @property
    def cb(self):
        """Code Builder's document, as far as the designer may see it."""
        return self.__dict__.setdefault("_cb_facade", CodeBuilderFacade(self))

    @property
    def designer_editor(self):
        ed = self.__dict__.get("_designer_editor")
        if ed is None:
            ed = self.__dict__["_designer_editor"] = UIDesignerEditor(AppEditorHost(self, "ui-designer"), CodeBuilderUIPort(self.cb))
        return ed

    @property
    def _dz_props_canvas(self):
        """The settings panel's canvas, for the wheel handler (None before the designer shows)."""
        ed = self.__dict__.get("_designer_editor")
        return getattr(ed, "_dz_props_canvas", None)

    def render_designer(self):
        self.designer_editor.render_designer()

    def designer_node(self):
        """The active node when the Blocks layer should show the designer for
        it (an attached UI node whose pack is installed), else None."""
        if not self.cb.in_node_view() or not self.cb.available():
            return None
        node = self.cb.active_node()
        if not ui_node.is_ui_node(node) or ui_node.is_detached(node) or self.behaviour_active():
            return None
        pack = self.cb.ui_pack()
        tree = ui_node.load_tree(node, pack) if pack else None
        if tree is None or tree.pack_id != pack.id or tree.read_only:
            return None
        return node

    # ---- behaviour: what the widgets do -------------------------------------
    def behaviour_active(self):
        """True while the open UI window shows its Behaviour view (the events
        and the function blocks they run) instead of the designer."""
        nid = self.__dict__.get("_behaviour_id")
        if not nid or not self.cb.available() or not self.cb.in_node_view():
            return False
        node = self.cb.active_node()
        return ui_node.is_ui_node(node) and node["id"] == nid and not ui_node.is_detached(node)

    def show_ui_behaviour(self):
        node = self.cb.active_node()
        if ui_node.is_ui_node(node):
            self._behaviour_id, self._behaviour_list = node["id"], None
            self.refresh_workspace()

    def hide_ui_behaviour(self):
        self._behaviour_id = None
        self.refresh_workspace()

    def behaviour_rows(self):
        node, pack = self.cb.context()
        tab = self.tabs[self.active_tab_index]
        return ui_node.event_rows(node, pack, lambda i: find_node_by_id(tab["nodes"], i))

    def behaviour_target_list(self):
        """The block list the palette adds to while Behaviour is shown: the body
        last clicked, else the first function body there is, else None."""
        if not self.behaviour_active():
            return None
        lists = [r["handler"]["blocks"] for r in self.behaviour_rows()
                 if r["handler"] and not r["is_window"] and isinstance(r["handler"].get("blocks"), list)]
        chosen = self.__dict__.get("_behaviour_list")
        if any(chosen is l for l in lists):
            return chosen
        return lists[0] if lists else None

    def set_behaviour_target(self, blocks):
        self._behaviour_list = blocks
        self._repaint_block_selection()

    def render_behaviour_view(self):
        """The Blocks layer for an attached UI window: its events, each with the
        blocks of the function it runs."""
        frame = self.workspace_frame
        node = self.cb.active_node()
        rows = self.behaviour_rows()
        bar = tk.Frame(frame, bg=DARK_BG)
        bar.pack(fill=tk.X, padx=10, pady=(8, 2))
        tk.Button(bar, text="\u21a9 Back to design", bg=DARK_ACCENT, fg="#ffffff", relief=tk.FLAT, cursor="hand2",
                  font=("Segoe UI", 9), command=self.hide_ui_behaviour).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(bar, text=f"What the widgets of {node['name']} do", bg=DARK_BG, fg=DARK_FG,
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        hint = ("Each event runs a function; its blocks are shown and edited here. Click an event, then add "
                "blocks from the palette. To link a widget to a function, select it in the designer and pick "
                "its event (for example On click).")
        if not rows:
            hint = ("No widget runs anything yet. In the designer, select a button, open its On click setting and "
                    "choose + New function\u2026; it then shows up here.")
        tk.Label(frame, text=hint, bg=DARK_BG, fg="#888888", font=("Segoe UI", 9), wraplength=620, justify=tk.LEFT,
                 anchor="w").pack(fill=tk.X, padx=14, pady=(0, 6))
        for r in rows:
            EventRowWidget(frame, r, self).pack(fill=tk.X, pady=4, padx=10)
        self._win_list = None
        self.block_count_label.config(text=f"{len(rows)} event{'s' if len(rows) != 1 else ''}")

    # ---- back from code-only ------------------------------------------------
    def reattach_ui_node(self):
        """Hand a code-only UI node back to the designer. If the code still has
        the shape the designer writes, it is read back (edits included); if not,
        the user may replace it with what the designer generates."""
        node, pack = self.cb.context()
        if not ui_node.is_ui_node(node) or not ui_node.is_detached(node):
            return
        resolve = self.cb.handler_resolver()
        names = {(ui_node.function_name(n) if ui_node.is_ui_node(n) else n["name"]): n["id"]
                 for n in self.cb.function_nodes(exclude=node)}
        text = self.cb.raw_code_text(node)
        tree, problems = (None, ["the node has blocks other than one code block"])
        if text is not None and pack is not None:
            tree, problems = ui_parse.read_back(node, pack, text, resolve, names.get,
                                                previous=ui_node.load_tree(node, pack))
        if tree is not None:
            if not messagebox.askyesno(
                    "Back to the designer",
                    "The code still has the shape the designer writes, so it can be read back.\n\n"
                    "The designer will pick up your changes to it. Continue?"):
                return
            ui_node.store_tree(node, tree)
        else:
            if not messagebox.askyesno(
                    "Back to the designer",
                    "The designer can't read this code back:\n\n  " + (problems[0] if problems else "unknown reason") +
                    "\n\nIt can take over again, but then the code is replaced by what the designer "
                    "generates and your edits to the code are lost.\n\nReplace the code?"):
                return
        ui_node.reattach(node)
        self.cb.forget_generated(node)
        self.designer_editor.reset()
        self.cb.mark_dirty()
        self.refresh_workspace()
