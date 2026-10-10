"""Canvas groups on the Files and Nodes layers (UI side, see groups_model)."""
from tkinter import simpledialog

import groups_model as gm
from ui_common import DARK_BG


class GroupsMixin:
    def _groups_ctx(self):
        """(group list, level key) of the canvas layer being shown."""
        if self.view_mode == "files":
            ws = self.workspaces[self.active_ws_index]
            return ws.setdefault("groups", []), ""
        tab = self.tabs[self.active_tab_index]
        path = tab.get("file_view_path") or []
        return tab.setdefault("groups", []), "/".join(str(p) for p in path)

    def _find_group(self, gid):
        lst, _ = self._groups_ctx()
        return next((g for g in lst if g["id"] == gid), None)

    # ---- drawing (called first, so boxes end up on top) -----------------
    def draw_groups(self):
        self._group_items = {}
        lst, level = self._groups_ctx()
        for g in gm.groups_for_level(lst, level):
            self._draw_group(g)

    def _draw_group(self, g):
        c = self.workspace_canvas
        col = g["color"]
        base = ("fileview", "group", "g_" + g["id"])
        body = c.create_rectangle(0, 0, 1, 1, fill=gm.blend(col, DARK_BG, 0.16), outline=col,
                                  tags=base + ("group_body",))
        title = c.create_rectangle(0, 0, 1, 1, fill=gm.blend(col, DARK_BG, 0.4), outline=col,
                                   tags=base + ("group_title",))
        label = c.create_text(0, 0, text=g["label"], anchor="w", fill="#e8e8e8",
                              font=self._zfont(11, "bold"), tags=base + ("group_title",))
        handle = c.create_polygon(0, 0, 0, 0, 0, 0, fill=col, outline="",
                                  tags=base + ("group_handle",))
        self._group_items[g["id"]] = {"body": body, "title": title, "label": label, "handle": handle}
        self._place_group(g)
        gid = g["id"]
        for item in (title, label):
            c.tag_bind(item, "<ButtonPress-1>", lambda e, i=gid: self._group_press(e, i, "move"))
            c.tag_bind(item, "<B1-Motion>", lambda e, i=gid: self._group_motion(e, i))
            c.tag_bind(item, "<ButtonRelease-1>", lambda e, i=gid: self._group_release(e, i))
            c.tag_bind(item, "<Double-Button-1>", lambda e, i=gid: self.rename_group(i))
        c.tag_bind(handle, "<ButtonPress-1>", lambda e, i=gid: self._group_press(e, i, "resize"))
        c.tag_bind(handle, "<B1-Motion>", lambda e, i=gid: self._group_motion(e, i))
        c.tag_bind(handle, "<ButtonRelease-1>", lambda e, i=gid: self._group_release(e, i))
        c.tag_bind(handle, "<Enter>", lambda e: c.configure(cursor="bottom_right_corner"))
        c.tag_bind(handle, "<Leave>", lambda e: c.configure(cursor=""))

    def _place_group(self, g):
        c, z = self.workspace_canvas, self.canvas_zoom
        it = self._group_items.get(g["id"])
        if not it:
            return
        x0, y0 = g["x"] * z, g["y"] * z
        x1, y1 = x0 + g["w"] * z, y0 + g["h"] * z
        th = self._zi(30)
        hs = self._zi(14)
        c.coords(it["body"], x0, y0, x1, y1)
        c.coords(it["title"], x0, y0, x1, y0 + th)
        c.coords(it["label"], x0 + self._zi(10), y0 + th / 2)
        c.coords(it["handle"], x1, y1 - hs, x1, y1, x1 - hs, y1)

    # ---- create / edit ----------------------------------------------------
    def add_group(self, pos):
        lst, level = self._groups_ctx()
        g = gm.make_group(lst, pos[0], pos[1], level=level)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return g

    def rename_group(self, gid):
        g = self._find_group(gid)
        if g is None:
            return
        name = simpledialog.askstring("Rename group", "Group label:",
                                      initialvalue=g["label"], parent=self)
        if name is None:
            return
        g["label"] = name.strip() or g["label"]
        self.workspace_canvas.itemconfigure(self._group_items[gid]["label"], text=g["label"])
        self.mark_active_tab_dirty()

    def set_group_color(self, gid, color):
        g = self._find_group(gid)
        if g is None or color not in [c for _, c in gm.GROUP_COLORS]:
            return
        g["color"] = color
        self.refresh_workspace()
        self.mark_active_tab_dirty()

    def delete_group(self, gid):
        lst, _ = self._groups_ctx()
        lst[:] = [g for g in lst if g["id"] != gid]
        self.mark_active_tab_dirty()
        self.refresh_workspace()

    def build_group_menu(self, gid):
        menu = self._new_menu(self)
        menu.add_command(label="Rename...", command=lambda: self.rename_group(gid))
        sub = self._new_menu(menu)
        for name, col in gm.GROUP_COLORS:
            sub.add_command(label=name, foreground=col,
                            command=lambda c=col: self.set_group_color(gid, c))
        menu.add_cascade(label="Color", menu=sub)
        menu.add_separator()
        menu.add_command(label="Delete group", command=lambda: self.delete_group(gid))
        return menu

    def _group_title_at(self, event):
        """Group id whose title bar / resize handle is under the pointer."""
        c = self.workspace_canvas
        if getattr(event, "widget", None) is not c:
            return None
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        for item in reversed(c.find_overlapping(x, y, x, y)):
            tags = c.gettags(item)
            if "group_title" in tags or "group_handle" in tags:
                return next((t[2:] for t in tags if t.startswith("g_")), None)
        return None

    # ---- drag: title moves the group AND the boxes inside; handle resizes -
    def _group_boxes(self):
        """[(container dict with canvas_x/y, window id, box widget)] shown now."""
        out = []
        if self.view_mode == "files":
            for idx, (wid, box) in getattr(self, "_filesview_boxes", {}).items():
                if 0 <= idx < len(self.tabs):
                    out.append((self.tabs[idx], wid, box))
        else:
            tab = self.tabs[self.active_tab_index]
            from nodes_model import find_node_by_id
            for nid, (wid, box) in getattr(self, "_fileview_boxes", {}).items():
                n = find_node_by_id(tab["nodes"], nid)
                if n is not None:
                    out.append((n, wid, box))
        return out

    def _group_press(self, e, gid, mode):
        g = self._find_group(gid)
        if g is None:
            return
        z = self.canvas_zoom
        inside = []
        if mode == "move":
            for d, wid, box in self._group_boxes():
                if "canvas_x" in d and gm.contains_center(
                        g, d["canvas_x"], d["canvas_y"],
                        box.winfo_reqwidth() / z, box.winfo_reqheight() / z):
                    inside.append((d, wid, d["canvas_x"], d["canvas_y"]))
        self._gdrag = {"gid": gid, "mode": mode, "sx": e.x_root, "sy": e.y_root,
                       "x0": g["x"], "y0": g["y"], "w0": g["w"], "h0": g["h"],
                       "inside": inside, "moved": False}

    def _group_motion(self, e, gid):
        st = getattr(self, "_gdrag", None)
        g = self._find_group(gid)
        if not st or st["gid"] != gid or g is None:
            return
        dx, dy = e.x_root - st["sx"], e.y_root - st["sy"]
        if not st["moved"] and abs(dx) <= 3 and abs(dy) <= 3:
            return
        st["moved"] = True
        z = self.canvas_zoom
        if st["mode"] == "resize":
            gm.resized(g, st["w0"] + dx / z, st["h0"] + dy / z)
            self._place_group(g)
            return
        g["x"], g["y"] = st["x0"] + dx / z, st["y0"] + dy / z
        self._place_group(g)
        for d, wid, bx, by in st["inside"]:
            d["canvas_x"], d["canvas_y"] = bx + dx / z, by + dy / z
            self.workspace_canvas.coords(wid, d["canvas_x"] * z, d["canvas_y"] * z)
        if st["inside"]:
            (self.draw_file_wires if self.view_mode == "files" else self.draw_wires)()

    def _group_release(self, e, gid):
        st = getattr(self, "_gdrag", None)
        self._gdrag = None
        if st and st["moved"]:
            self.mark_active_tab_dirty()
            self._update_fileview_scrollregion()
            self.redraw_grid()
