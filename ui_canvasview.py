"""Files/Nodes canvas: wheel zoom, coordinate grid, view anchoring."""
import tkinter as tk
import tkinter.font as tkfont
from canvas_view import (anchor_view_origin, box_look, clamp_zoom, grid_step, grid_values,
                         lod_mode, zoom_after_wheel)
from nodes_model import find_node_by_id

GRID_COLOR = "#262626"
GRID_MAJOR_COLOR = "#2f2f2f"
AXIS_COLOR = "#3b5b7a"
LABEL_COLOR = "#6b6b6b"


class CanvasViewMixin:
    canvas_zoom = 1.0
    _rendered_zoom = 1.0
    _zoom_job = None
    _zoom_anchor = None
    _grid_job = None
    _zoom_fonts = None
    _zoom_hooks = None
    _rendered_look = None

    # ---- scaling helpers used when building boxes ------------------------
    # Boxes are NOT rebuilt on zoom: their fonts are shared Font objects
    # (one per base size/style) that are resized in place, and every other
    # zoom-dependent size (header width/height, paddings) is registered as a
    # "zoom hook" that is re-run on zoom. Only a change of LOOK (full box <->
    # names-only/gray when crossing LOD_ZOOM) rebuilds the boxes.
    def _zi(self, n):
        return max(1, int(round(n * self.canvas_zoom)))

    def _zpad(self, v):
        return tuple(self._zi(x) if x else 0 for x in v) if isinstance(v, (tuple, list)) else \
            (self._zi(v) if v else 0)

    def _zfont_size(self, size):
        return max(5, int(round(size * self.canvas_zoom)))

    def _zfont(self, size, *style):
        """Shared, zoom-following font for canvas boxes and group titles."""
        if self._zoom_fonts is None:
            self._zoom_fonts = {}
        key = (size,) + tuple(style)
        f = self._zoom_fonts.get(key)
        want = self._zfont_size(size)
        if f is None:
            f = tkfont.Font(self, family="Segoe UI", size=want,
                            weight="bold" if "bold" in style else "normal",
                            slant="italic" if "italic" in style else "roman")
            self._zoom_fonts[key] = f
        elif int(f.cget("size")) != want:
            f.configure(size=want)
        return f

    def _zhook(self, widget, fn):
        """Run fn now and again after every zoom (while widget lives)."""
        fn()
        if self._zoom_hooks is None:
            self._zoom_hooks = []
        self._zoom_hooks.append((widget, fn))

    def _zpack(self, widget, **opts):
        """pack() whose padx/pady/ipadx/ipady follow the zoom."""
        scaled = {k: opts.pop(k) for k in ("padx", "pady", "ipadx", "ipady") if k in opts}
        widget.pack(**opts)
        if scaled:
            self._zhook(widget, lambda: widget.pack_configure(
                **{k: self._zpad(v) for k, v in scaled.items()}))

    def _zconf(self, widget, add=0, **sizes):
        """configure(width=..., height=...) that follows the zoom (+add px)."""
        self._zhook(widget, lambda: widget.configure(
            **{k: self._zi(v) + add for k, v in sizes.items()}))

    def _look_now(self):
        """"full", "names" or "gray" for the current zoom and setting."""
        return box_look(self.canvas_zoom, lod_mode(getattr(self, "settings", {})))

    def _lod_compact(self):
        """True when boxes should be drawn as just a title strip (zoomed far out)."""
        return self._look_now() != "full"

    def _lod_gray(self):
        return self._look_now() == "gray"

    def _fix_compact_size(self, box, header, model_width):
        """Give a compact box an exact size (title strip only), so zoomed-out
        boxes scale with the zoom instead of ballooning around their text."""
        self._zconf(header, width=model_width, height=36)
        self._zconf(box, add=4, width=model_width, height=36)
        box.pack_propagate(False)

    def _begin_canvas_render(self):
        """Called by render_file_view/render_files_view before building."""
        self._zoom_hooks = []
        self._rendered_zoom = self.canvas_zoom
        self._rendered_look = self._look_now()

    def _canvas_box_widgets(self):
        out = [b for _w, b in (getattr(self, "_fileview_boxes", None) or {}).values()]
        out += [b for _w, b in (getattr(self, "_filesview_boxes", None) or {}).values()]
        return out

    def canvas_layer_active(self):
        """True on the Files and Nodes layers' canvas (not their code views)."""
        vm = getattr(self, "view_mode", None)
        return (vm == "files" and not getattr(self, "files_view_code_mode", False)) or \
               (vm == "file" and not getattr(self, "file_view_code_mode", False))

    # ---- zoom ------------------------------------------------------------
    def canvas_wheel_zoom(self, step):
        """Mouse wheel on the canvas layers = zoom around the pointer.
        Returns False when the current layer isn't a zoomable canvas."""
        if not self.canvas_layer_active():
            return False
        c = self.workspace_canvas
        sx = self.winfo_pointerx() - c.winfo_rootx()
        sy = self.winfo_pointery() - c.winfo_rooty()
        self.zoom_step(step, sx, sy)
        return True

    def zoom_step(self, step, sx, sy):
        z0 = self.canvas_zoom
        z1 = zoom_after_wheel(z0, step)
        if z1 == z0:
            return
        c = self.workspace_canvas
        # The canvas is still laid out at the last applied zoom until the
        # pending resize runs, so the model point under the pointer is read
        # at that zoom. Several fast wheel steps collapse into ONE resize.
        gz = self._rendered_zoom or 1.0
        mx, my = c.canvasx(sx) / gz, c.canvasy(sy) / gz
        self._zoom_anchor = (mx, my, sx, sy)
        self.canvas_zoom = z1
        self._cancel_zoom_job()
        self._zoom_job = self.after_idle(self.apply_zoom)

    def _cancel_zoom_job(self):
        if self._zoom_job is not None:
            try:
                self.after_cancel(self._zoom_job)
            except tk.TclError:
                pass
            self._zoom_job = None

    def set_zoom(self, z):
        """Programmatic zoom (keeps the view's top-left model point)."""
        self.canvas_zoom = clamp_zoom(z)
        self._zoom_anchor = None
        self.apply_zoom()

    def apply_zoom(self):
        self._cancel_zoom_job()
        anchor, self._zoom_anchor = self._zoom_anchor, None
        if not self.canvas_layer_active():
            return
        c = self.workspace_canvas
        if anchor is None:
            rz = self._rendered_zoom or 1.0
            anchor = (c.canvasx(0) / rz, c.canvasy(0) / rz, 0, 0)
        if self._look_now() != self._rendered_look or not self._canvas_box_widgets():
            self.rerender_canvas_layer()
        else:
            self.rescale_canvas_layer()
        mx, my, sx, sy = anchor
        z = self.canvas_zoom
        self._set_view_origin(anchor_view_origin(mx, sx, z), anchor_view_origin(my, sy, z))
        self.redraw_grid()

    def rescale_canvas_layer(self):
        """Resize the boxes that are already on the canvas to the current
        zoom - nothing is destroyed or rebuilt, so nothing flashes."""
        z = self.canvas_zoom
        for key, f in (self._zoom_fonts or {}).items():
            want = self._zfont_size(key[0])
            if int(f.cget("size")) != want:
                f.configure(size=want)
        alive = []
        for w, fn in (self._zoom_hooks or []):
            try:
                if w.winfo_exists():
                    fn()
                    alive.append((w, fn))
            except tk.TclError:
                pass
        self._zoom_hooks = alive
        c = self.workspace_canvas
        if self.view_mode == "files":
            for idx, (win, _b) in self._filesview_boxes.items():
                if 0 <= idx < len(self.tabs):
                    t = self.tabs[idx]
                    c.coords(win, t["canvas_x"] * z, t["canvas_y"] * z)
        else:
            tab = self.tabs[self.active_tab_index]
            for nid, (win, _b) in self._fileview_boxes.items():
                n = find_node_by_id(tab["nodes"], nid)
                if n:
                    c.coords(win, n["canvas_x"] * z, n["canvas_y"] * z)
        c.delete("group")
        self.draw_groups()
        self.update_idletasks()      # widgets take their new sizes before wires use them
        if self.view_mode == "files":
            self.draw_file_wires()
        else:
            self.draw_wires()
        self._update_fileview_scrollregion()
        self._rendered_zoom = z

    def rerender_canvas_layer(self):
        """Rebuild the canvas boxes/wires (cheaper than refresh_workspace).
        The new boxes are built and drawn BEFORE the old ones are removed,
        so the switch does not flash an empty canvas."""
        c = self.workspace_canvas
        old = self._canvas_box_widgets()
        c.addtag_withtag("fileview_old", "fileview")
        c.dtag("fileview_old", "fileview")
        if self.view_mode == "files":
            self.render_files_view()
        else:
            self.render_file_view()
        self.update_idletasks()
        c.delete("fileview_old")
        for w in old:
            try:
                w.destroy()
            except tk.TclError:
                pass

    def _set_view_origin(self, tlx, tly):
        c = self.workspace_canvas
        dx, dy = tlx - c.canvasx(0), tly - c.canvasy(0)
        c.scan_mark(0, 0)
        c.scan_dragto(int(round(-dx)), int(round(-dy)), gain=1)
        self._expand_scrollregion_to_view()

    def _expand_scrollregion_to_view(self):
        c = self.workspace_canvas
        vx0, vy0 = c.canvasx(0), c.canvasy(0)
        vx1, vy1 = c.canvasx(c.winfo_width()), c.canvasy(c.winfo_height())
        try:
            sx0, sy0, sx1, sy1 = [float(v) for v in str(c.cget("scrollregion")).split()]
        except ValueError:
            sx0, sy0, sx1, sy1 = vx0, vy0, vx1, vy1
        c.configure(scrollregion=(min(sx0, vx0), min(sy0, vy0), max(sx1, vx1), max(sy1, vy1)))

    # ---- coordinate grid -------------------------------------------------
    def install_grid(self):
        c = self.workspace_canvas
        c.configure(xscrollcommand=lambda *a: self.schedule_grid())
        c.bind("<Configure>", lambda e: self.schedule_grid(), add="+")

    def schedule_grid(self):
        if self._grid_job is None:
            self._grid_job = self.after_idle(self._run_grid_job)

    def _run_grid_job(self):
        self._grid_job = None
        try:
            self.redraw_grid()
        except tk.TclError:
            pass

    def redraw_grid(self):
        """Faint grid + brighter x/y axes through 0,0 behind the boxes; the
        numbers along the top/left edge are the 'show_coords' setting."""
        c = self.workspace_canvas
        c.delete("grid")
        if not self.canvas_layer_active() or not c.find_withtag("fileview"):
            return
        z = self.canvas_zoom
        w, h = c.winfo_width(), c.winfo_height()
        x0, y0 = c.canvasx(0), c.canvasy(0)
        step = grid_step(z)
        xs = grid_values(x0 / z, (x0 + w) / z, step)
        ys = grid_values(y0 / z, (y0 + h) / z, step)
        major = step * 5
        show = bool(self.settings.get("show_coords", False))
        font = ("Segoe UI", 8)
        for m in xs:
            x = m * z
            col = AXIS_COLOR if m == 0 else (GRID_MAJOR_COLOR if m % major == 0 else GRID_COLOR)
            c.create_line(x, y0, x, y0 + h, fill=col, tags=("grid",))
            if show:
                c.create_text(x + 3, y0 + 2, text=str(int(m)), anchor="nw", fill=LABEL_COLOR,
                              font=font, tags=("grid",))
        for m in ys:
            y = m * z
            col = AXIS_COLOR if m == 0 else (GRID_MAJOR_COLOR if m % major == 0 else GRID_COLOR)
            c.create_line(x0, y, x0 + w, y, fill=col, tags=("grid",))
            if show:
                c.create_text(x0 + 3, y + 2, text=str(int(m)), anchor="nw", fill=LABEL_COLOR,
                              font=font, tags=("grid",))
        c.tag_lower("grid")

    # ---- hit-testing for panning ------------------------------------------
    def _pan_blocking_items(self, x, y):
        """Canvas items under the point that should stop a pan from starting
        (boxes, wires, ...). The grid and group backgrounds never do."""
        c = self.workspace_canvas
        out = []
        for i in c.find_overlapping(x - 2, y - 2, x + 2, y + 2):
            if i == getattr(self, "workspace_frame_window_id", None):
                continue
            tags = c.gettags(i)
            if "grid" in tags or "group_body" in tags:
                continue
            out.append(i)
        return out
