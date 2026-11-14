"""Smooth wheel zoom on the Files/Nodes canvas.

The boxes are real widgets (about 14 each). Resizing all of them on every wheel notch cost ~40 ms per notch at
150 nodes and made them breathe: widths follow the zoom exactly but heights follow font rounding, so the boxes drifted
6-8% off the positions. While the wheel is turning, the boxes are therefore hidden and drawn as flat stand-ins
(frame, title strip, name) whose size is exactly model size x zoom; wires and groups are scaled with the canvas
and the grid is redrawn. apply_zoom() puts the real boxes back once at the final zoom."""
import tkinter as tk

HEADER_H = 36                   # a box's title strip, in model units
TITLE_MAX = 30


class ZoomPreviewMixin:
    _zprev = None               # while a preview shows: {"entries": [...], "zoom": the zoom the canvas items are at}

    def shown_canvas_zoom(self):
        """The zoom the items on the canvas are at right now (a preview may be ahead of the real boxes)."""
        if self._zprev is not None:
            return self._zprev["zoom"]
        return self._rendered_zoom or 1.0

    def _preview_sources(self):
        boxes = self._filesview_boxes if self.view_mode == "files" else self._fileview_boxes
        return list((boxes or {}).values())

    @staticmethod
    def _preview_text(box):
        """The first label's text in the box: its name."""
        todo = list(box.winfo_children())
        while todo:
            w = todo.pop(0)
            if w.winfo_class() == "Label" and w.cget("text"):
                return str(w.cget("text")).replace("\U0001F4C4 ", "")[:TITLE_MAX]
            todo.extend(w.winfo_children())
        return ""

    def _zoom_preview_begin(self):
        c = self.workspace_canvas
        rz = self._rendered_zoom or 1.0
        entries = []
        for win, box in self._preview_sources():
            try:
                x, y = c.coords(win)
                w, h = box.winfo_width(), box.winfo_height()
                if w < 20 or h < 10:                      # never shown yet: use what it asked for
                    w, h = box.winfo_reqwidth(), box.winfo_reqheight()
                kids = box.winfo_children()
                strip = kids[0].cget("bg") if kids else "#2a5a8a"
                body = box.cget("bg")
                edge = box.cget("highlightbackground")
                title = self._preview_text(box)
            except tk.TclError:
                continue
            frame = c.create_rectangle(0, 0, 1, 1, fill=body, outline=edge, width=2, tags=("zprev",))
            band = c.create_rectangle(0, 0, 1, 1, fill=strip, outline="", tags=("zprev",))
            name = c.create_text(0, 0, text=title, anchor="w", fill="#ffffff", tags=("zprev",))
            c.itemconfigure(win, state="hidden")
            entries.append({"win": win, "x": x / rz, "y": y / rz, "w": w / rz, "h": h / rz,
                            "frame": frame, "band": band, "name": name})
        self._zprev = {"entries": entries, "zoom": rz}

    def zoom_preview_update(self, mx, my, sx, sy, z):
        """Show the canvas at zoom z with the model point (mx, my) at screen point (sx, sy)."""
        if not self.canvas_layer_active():
            return
        c = self.workspace_canvas
        if self._zprev is None:
            self._zoom_preview_begin()
        zp = self._zprev["zoom"]
        self._set_view_origin(mx * z - sx, my * z - sy)
        size = max(5, int(round(10 * z)))
        for e in self._zprev["entries"]:
            x0, y0 = e["x"] * z, e["y"] * z
            x1, y1 = x0 + e["w"] * z, y0 + e["h"] * z
            band_h = min(HEADER_H * z, e["h"] * z)
            c.coords(e["frame"], x0, y0, x1, y1)
            c.coords(e["band"], x0, y0, x1, y0 + band_h)
            c.coords(e["name"], x0 + 8 * z, y0 + band_h / 2)
            c.itemconfigure(e["name"], font=("Segoe UI", size, "bold"), state="normal" if size >= 6 else "hidden")
        if zp:
            f = z / zp
            c.scale("wire", 0, 0, f, f)
            c.scale("group", 0, 0, f, f)
        self._zprev["zoom"] = z
        self.redraw_grid()

    def zoom_preview_end(self):
        """Remove the stand-ins and show the real boxes again. The wires and groups go back to the scale of the real
        boxes, which is what rescale_canvas_layer / rerender_canvas_layer expect."""
        prev, self._zprev = self._zprev, None
        if prev is None:
            return
        c = self.workspace_canvas
        c.delete("zprev")
        for e in prev["entries"]:
            try:
                c.itemconfigure(e["win"], state="normal")
            except tk.TclError:
                pass
        rz = self._rendered_zoom or 1.0
        if prev["zoom"]:
            f = rz / prev["zoom"]
            c.scale("wire", 0, 0, f, f)
            c.scale("group", 0, 0, f, f)
