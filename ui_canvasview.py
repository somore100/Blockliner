"""Files/Nodes canvas: wheel zoom, coordinate grid, view anchoring."""
import tkinter as tk
from canvas_view import anchor_view_origin, clamp_zoom, grid_step, grid_values, zoom_after_wheel

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

    # ---- scaling helpers used when building boxes ------------------------
    def _zi(self, n):
        return max(1, int(round(n * self.canvas_zoom)))

    def _zfont(self, size, *style):
        return ("Segoe UI", max(5, int(round(size * self.canvas_zoom))), *style)

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
        rz = self._rendered_zoom or 1.0
        self._zoom_anchor = (c.canvasx(sx) / rz, c.canvasy(sy) / rz, sx, sy)
        self.canvas_zoom = z1
        if self._zoom_job is None:
            self._zoom_job = self.after(15, self.apply_zoom)

    def set_zoom(self, z):
        """Programmatic zoom (keeps the view's top-left model point)."""
        self.canvas_zoom = clamp_zoom(z)
        self._zoom_anchor = None
        self.apply_zoom()

    def apply_zoom(self):
        if self._zoom_job is not None:
            try:
                self.after_cancel(self._zoom_job)
            except tk.TclError:
                pass
            self._zoom_job = None
        anchor, self._zoom_anchor = self._zoom_anchor, None
        if not self.canvas_layer_active():
            return
        c = self.workspace_canvas
        if anchor is None:
            rz = self._rendered_zoom or 1.0
            anchor = (c.canvasx(0) / rz, c.canvasy(0) / rz, 0, 0)
        self.rerender_canvas_layer()
        mx, my, sx, sy = anchor
        z = self.canvas_zoom
        self._set_view_origin(anchor_view_origin(mx, sx, z), anchor_view_origin(my, sy, z))
        self.redraw_grid()

    def rerender_canvas_layer(self):
        """Rebuild only the canvas boxes/wires (cheaper than refresh_workspace)."""
        c = self.workspace_canvas
        c.delete("fileview")
        if self.view_mode == "files":
            self.render_files_view()
        else:
            self.render_file_view()
        self._rendered_zoom = self.canvas_zoom

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
