"""The UI designer inside the app: finds out when an attached UI node should show
the designer, hosts it in the workspace canvas, and takes a node back from
code-only. The designer itself is designer_editor.UIDesignerEditor."""
import tkinter as tk
from tkinter import messagebox

import ui_node
import ui_parse
from codebuilder_api import CodeBuilderFacade
from designer_editor import UIDesignerEditor
from designer_port import CodeBuilderUIPort


class AppDesignerHost:
    """What the designer needs from the app's window."""

    def __init__(self, app):
        self._app = app

    @property
    def frame(self):
        return self._app.workspace_frame

    def after(self, ms, func=None, *args):
        return self._app.after(ms, func, *args)

    def after_idle(self, func, *args):
        return self._app.after_idle(func, *args)

    def bell(self):
        self._app.bell()

    def winfo_rgb(self, colour):
        return self._app.winfo_rgb(colour)

    def view_width(self):
        return self._app.workspace_canvas.winfo_width() - 2

    def fit(self):
        self._app._dz_fit()

    def refresh(self):
        self._app.refresh_workspace()

    def showing(self):
        return self._app.designer_node() is not None


class DesignerMixin:

    @property
    def cb(self):
        """Code Builder's document, as far as the designer may see it."""
        return self.__dict__.setdefault("_cb_facade", CodeBuilderFacade(self))

    @property
    def designer_editor(self):
        ed = self.__dict__.get("_designer_editor")
        if ed is None:
            ed = self.__dict__["_designer_editor"] = UIDesignerEditor(AppDesignerHost(self), CodeBuilderUIPort(self.cb))
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
        if not ui_node.is_ui_node(node) or ui_node.is_detached(node):
            return None
        pack = self.cb.ui_pack()
        tree = ui_node.load_tree(node, pack) if pack else None
        if tree is None or tree.pack_id != pack.id or tree.read_only:
            return None
        return node

    # ---- the workspace canvas while the designer shows ----------------------
    def lock_workspace_for_designer(self, on):
        """The designer fills the workspace canvas: no scrollbar, wheel or
        drag-panning (see ui.py _install_wheel, ui_canvas _pan_press)."""
        was = getattr(self, "_workspace_locked", False)
        self._workspace_locked = on
        if not getattr(self, "_dz_fit_bound", False):
            self.workspace_canvas.bind("<Configure>", self._dz_fit, add="+")
            self._dz_fit_bound = True
        if on and not was:
            self.workspace_scrollbar.pack_forget()
        elif was and not on:
            self.workspace_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=self.workspace_canvas)
            self.workspace_canvas.itemconfigure(self.workspace_frame_window_id, width=self.workspace_frame_width)

    def _dz_fit(self, _event=None):
        """Size the designer to the visible canvas and pin the view at (0, 0)."""
        if not getattr(self, "_workspace_locked", False):
            return
        c = self.workspace_canvas
        w, h = c.winfo_width() - 2, c.winfo_height() - 2         # inside the 1px highlight border
        if w < 10 or h < 10:
            return
        c.itemconfigure(self.workspace_frame_window_id, width=w, height=h)
        if c.canvasx(0) != 0 or c.canvasy(0) != 0:
            self._set_view_origin(0, 0)
        c.configure(scrollregion=(0, 0, w, h))
        self.designer_editor.on_resized(w)

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
