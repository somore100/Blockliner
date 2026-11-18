"""Nodes layer with many nodes: only the boxes near the view are built as widgets.

A box is ~25 Tk widgets, so 1000 nodes meant ~28k widgets and a ~1.5 s rebuild on every refresh. Above CULL_AT nodes
the boxes inside the view (plus a margin of one screen) are built; the rest stay as plain model data ("ghosts").
Wires still run to ghosts (drawn to where the box would be), and panning, zooming and editing build / drop boxes as
the view moves. Below CULL_AT nothing changes: every box is built, as before."""
import tkinter as tk

from canvas_view import NODE_W
from nodes_model import find_node_by_id

CULL_AT = 80             # shown nodes above which boxes are built only near the view
BUILD_MARGIN = 0.5       # screens beyond the view that get real boxes
KEEP_MARGIN = 1.25       # boxes farther out than this are dropped again
GHOST_H = 110            # model height of a box that is not built (wire anchor, hit-test)
CULL_DELAY_MS = 120


class Ghost:
    """Stands in for a box that is not built, where only its size is asked."""
    def __init__(self, w, h):
        self._w, self._h = int(w), int(h)

    def winfo_width(self):
        return self._w

    def winfo_height(self):
        return self._h


class CullMixin:
    def _ghosts(self):
        return self.__dict__.setdefault("_ghost_ids", set())

    def _wireable(self, nid):
        """True when a wire can end at this node: its box exists, or it is a ghost."""
        return nid in self._fileview_boxes or nid in self._ghosts()

    def _box_pair(self, nid):
        pair = self._fileview_boxes.get(nid)
        if pair:
            return pair
        n = find_node_by_id(self.tabs[self.active_tab_index]["nodes"], nid) or {}
        z = self.canvas_zoom
        return None, Ghost((n.get("canvas_w") or NODE_W) * z, (n.get("canvas_h") or GHOST_H) * z)

    def _cull_on(self, nodes):
        return len(nodes) > CULL_AT

    def _view_rect(self, margin):
        """The visible part of the canvas, grown by `margin` screens, in model units."""
        c, z = self.workspace_canvas, self.canvas_zoom
        w, h = max(c.winfo_width(), 700), max(c.winfo_height(), 450)
        x0, y0 = c.canvasx(0) / z, c.canvasy(0) / z
        mw, mh = w / z * margin, h / z * margin
        return (x0 - mw, y0 - mh, x0 + w / z + mw, y0 + h / z + mh)

    @staticmethod
    def _node_hits(n, rect):
        x, y = n.get("canvas_x", 0), n.get("canvas_y", 0)
        w, h = n.get("canvas_w") or NODE_W, n.get("canvas_h") or 260
        return x < rect[2] and x + w > rect[0] and y < rect[3] and y + h > rect[1]

    def make_node_box(self, node, nodes=None, rect=None):
        """Build the node's box, or leave it as a ghost when it is far from the view (many nodes)."""
        if rect is None and nodes is not None and self._cull_on(nodes):
            rect = self._view_rect(BUILD_MARGIN)
        if rect is not None and not self._node_hits(node, rect):
            self._ghosts().add(node["id"])
            return False
        self._ghosts().discard(node["id"])
        self.create_fileview_node_box(node)
        return True

    def schedule_cull(self):
        if self.__dict__.get("_cull_job") is None and self.__dict__.get("_ghost_ids") is not None:
            try:
                self._cull_job = self.after(CULL_DELAY_MS, self.cull_update)
            except tk.TclError:
                pass

    def cull_update(self):
        """Build the boxes that came into view and drop the ones that left it; redraw the wires if anything changed."""
        self._cull_job = None
        try:
            if self.view_mode != "file" or self.file_view_code_mode or not self.canvas_layer_active():
                return
            tab = self.tabs[self.active_tab_index]
            nodes = self.get_current_node_list(tab)
            ghosts = self._ghosts()
            if not ghosts and not self._cull_on(nodes):
                return
            build = None if not self._cull_on(nodes) else self._view_rect(BUILD_MARGIN)
            keep = self._view_rect(KEEP_MARGIN)
            busy = {self.__dict__.get("_wire_drag_source"), self.__dict__.get("_wire_drag_hover_id")}
            changed, doomed = False, []
            for n in nodes:
                nid = n["id"]
                if nid in self._fileview_boxes:
                    if build is not None and nid not in busy and not self._node_hits(n, keep):
                        win, box = self._fileview_boxes.pop(nid)
                        self.workspace_canvas.delete(win)
                        doomed.append(box)
                        ghosts.add(nid)
                        changed = True
                elif build is None or self._node_hits(n, build):
                    self.make_node_box(n, rect=None)
                    changed = True
            ghosts &= {n["id"] for n in nodes}
            if doomed:
                self.destroy_boxes(doomed)
            if changed:
                self.workspace_frame.update_idletasks()
                self.workspace_canvas.delete("group")
                self.draw_groups()
                self.draw_wires()
                self._update_fileview_scrollregion()
                for nid in self.selected_nodes():
                    self._paint_node_selection(nid)
        except tk.TclError:
            pass
