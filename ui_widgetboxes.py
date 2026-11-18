"""A UI window's widgets as their own draggable boxes on the Nodes layer ("▣ As boxes" on the window's box).

Each widget gets a small box (name, type, one line per event with a dot). A thin dotted line ties it to its window, and
a wire runs from every linked event to the function node that handles it. Drag a box by its title; its place is saved
with the window, as an offset from the window, so moving the window moves its widgets. Click the title (no drag) to open
the window in the designer on that widget. Empty dots make and link a function, as in the list. The pure part is
ui_node.widget_rows; the list mode (ui_open == True) is in ui_nodewidgets."""
import tkinter as tk

import ui_node
from canvas_view import NODE_W
from nodes_model import find_node_by_id
from ui_common import BLOCK_BG

BOX_W = 190                 # model width of a widget box
BOX_LIMIT = 40              # more widgets than this: the first ones get boxes, the rest stay in the designer
ROW_H = 20                  # model height of one event line
HEAD_H = 40                 # title + type line
GAP = 10
TITLE = "#1f7a6a"
LINKED = "#4ec9b0"
FREE = "#777777"
TIE = "#2a6a60"


def default_offsets(rows, window_w):
    """{widget id: [dx, dy]} - a column to the right of the window, each box as tall as its events need."""
    out, y = {}, 0
    for row in rows:
        out[row["id"]] = [window_w + 40, y]
        y += HEAD_H + ROW_H * max(1, len(row["events"])) + GAP
    return out


class WidgetBoxMixin:
    def widget_boxes(self):
        return self.__dict__.setdefault("_widget_boxes", {})

    # ---- the switch on the window's box -------------------------------------
    def toggle_ui_boxes(self, nid):
        node = find_node_by_id(self._ui_tab()["nodes"], nid)
        if node is None:
            return
        if node.get("ui_open") == "boxes":
            node.pop("ui_open", None)
        else:
            node["ui_open"] = "boxes"
        self.mark_active_tab_dirty()
        if not self.refresh_nodes_in_place(rebuild_ids=(nid,)):
            self.refresh_workspace()

    def _offsets(self, node, rows):
        offs = default_offsets(rows, node.get("canvas_w") or NODE_W)
        for wid, off in (node.get("ui_box_pos") or {}).items():
            if wid in offs and isinstance(off, (list, tuple)) and len(off) == 2:
                offs[wid] = list(off)
        return offs

    def widget_box_origin(self, node, wid):
        """Model position (x, y) a widget's box is drawn at, or None."""
        rows = ui_node.widget_rows(node, self._ui_pack_of(node), self._ui_lookup())[:BOX_LIMIT]
        off = self._offsets(node, rows).get(wid)
        if off is None:
            return None
        return node.get("canvas_x", 0) + off[0], node.get("canvas_y", 0) + off[1]

    # ---- build / clear -------------------------------------------------------
    def clear_widget_boxes(self, ui_id):
        reg = self.widget_boxes()
        gone = [k for k in reg if k[0] == ui_id]
        boxes = []
        for k in gone:
            win, box, _ports = reg.pop(k)
            self.workspace_canvas.delete(win)
            boxes.append(box)
        if boxes:
            self.destroy_boxes(boxes)

    def build_widget_boxes(self, node):
        """Boxes for one window (when it is in "boxes" mode and its code is still the designer's)."""
        if node.get("ui_open") != "boxes" or not ui_node.is_ui_node(node) or ui_node.is_detached(node):
            return
        rows = ui_node.widget_rows(node, self._ui_pack_of(node), self._ui_lookup())[:BOX_LIMIT]
        offs = self._offsets(node, rows)
        for row in rows:
            self._make_widget_box(node, row, offs[row["id"]])

    def _make_widget_box(self, node, row, off):
        z, nid, wid = self.canvas_zoom, node["id"], row["id"]
        box = tk.Frame(self.workspace_canvas, bg=BLOCK_BG, highlightthickness=2, highlightbackground=TITLE)
        head = tk.Label(box, text=f"{'▣' if row['screen'] else '▫'} {row['name']}", bg=TITLE, fg="#ffffff",
                        font=self._zfont(9, "bold"), anchor="w", cursor="fleur")
        head.pack(fill=tk.X)
        tk.Label(box, text=row["label"], bg=BLOCK_BG, fg="#888888", font=self._zfont(7), anchor="w").pack(fill=tk.X, padx=4)
        ports = []
        for ev in row["events"]:
            linked = bool(ev["handler"])
            text = f"{ev['label']} → {ev['handler']['name']}" if linked else (
                f"{ev['label']} → (missing)" if ev["handler_id"] else f"{ev['label']} +")
            lab = tk.Label(box, text=text + (" ●" if linked else " ○"), bg=BLOCK_BG, fg=LINKED if linked else FREE,
                           font=self._zfont(8), cursor="hand2", anchor="e")
            lab.pack(fill=tk.X, padx=4)
            if linked:
                lab.bind("<Button-1>", lambda _e, h=ev["handler_id"]: self.open_node(h))
                ports.append((lab, ev["handler_id"]))
            elif not ev["handler_id"]:
                lab.bind("<Button-1>", lambda _e, key=ev["key"]: self.link_new_ui_handler(nid, wid, key))
        self._zhook(box, lambda: box.configure(width=self._zi(BOX_W)))
        win = self.workspace_canvas.create_window(
            (node["canvas_x"] + off[0]) * z, (node["canvas_y"] + off[1]) * z, anchor="nw", window=box,
            tags=("fileview", "widget_box"))
        self.widget_boxes()[(nid, wid)] = (win, box, ports)
        self._bind_widget_box_drag(head, nid, wid)

    def _bind_widget_box_drag(self, head, nid, wid):
        st = {"drag": False, "x": 0, "y": 0, "off": [0, 0]}

        def press(e):
            node = find_node_by_id(self._ui_tab()["nodes"], nid)
            if node is None:
                return
            st.update(drag=False, x=e.x_root, y=e.y_root)
            o = self.widget_box_origin(node, wid) or (0, 0)
            st["off"] = [o[0] - node.get("canvas_x", 0), o[1] - node.get("canvas_y", 0)]

        def motion(e):
            dx, dy = e.x_root - st["x"], e.y_root - st["y"]
            if not st["drag"] and (abs(dx) > 4 or abs(dy) > 4):
                st["drag"] = True
            if not st["drag"]:
                return
            node = find_node_by_id(self._ui_tab()["nodes"], nid)
            if node is None:
                return
            z = self.canvas_zoom
            node.setdefault("ui_box_pos", {})[wid] = [round(st["off"][0] + dx / z, 1), round(st["off"][1] + dy / z, 1)]
            self.place_widget_boxes(nid)
            self.draw_widget_wires()

        def release(_e):
            if st["drag"]:
                self.mark_active_tab_dirty()
                self._update_fileview_scrollregion()
            else:
                self.open_ui_widget(nid, wid)
            st["drag"] = False

        head.bind("<ButtonPress-1>", press)
        head.bind("<B1-Motion>", motion)
        head.bind("<ButtonRelease-1>", release)

    # ---- placing and wires ---------------------------------------------------
    def place_widget_boxes(self, ui_id=None):
        """Put every widget box (of one window, or all) where its window and offset say, at the current zoom."""
        z, tab = self.canvas_zoom, self._ui_tab()
        for (nid, wid), (win, _box, _p) in list(self.widget_boxes().items()):
            if ui_id is not None and nid != ui_id:
                continue
            node = find_node_by_id(tab["nodes"], nid)
            o = self.widget_box_origin(node, wid) if node else None
            if o is not None:
                self.workspace_canvas.coords(win, o[0] * z, o[1] * z)

    def draw_widget_wires(self):
        c, z = self.workspace_canvas, self.canvas_zoom
        c.delete("uiwire")
        reg = self.widget_boxes()
        if not reg:
            return
        self.update_idletasks()
        for (nid, wid), (win, box, ports) in reg.items():
            if not self._wireable(nid):
                continue
            try:
                x, y = c.coords(win)
                bw, bh = box.winfo_width(), box.winfo_height()
                owner = self._fileview_boxes.get(nid)
                if owner is not None:
                    ox, oy = c.coords(owner[0])
                    ow, oh = owner[1].winfo_width(), owner[1].winfo_height()
                    c.create_line(ox + ow, oy + oh / 2, x, y + 12 * z, fill=TIE, dash=(2, 3), tags=("fileview", "uiwire"))
                for lab, hid in ports:
                    if not self._wireable(hid):
                        continue
                    node = find_node_by_id(self._ui_tab()["nodes"], hid)
                    if node is None:
                        continue
                    _w, hbox = self._box_pair(hid)
                    x0, y0 = x + bw, y + (lab.winfo_rooty() - box.winfo_rooty()) + lab.winfo_height() / 2
                    x1, y1 = node["canvas_x"] * z, node["canvas_y"] * z + (hbox.winfo_height() or 70) / 2
                    pull = max(abs(x1 - x0) * 0.5, 40)
                    c.create_line(*self._bezier_points((x0, y0), (x0 + pull, y0), (x1 - pull, y1), (x1, y1)),
                                  smooth=True, fill=LINKED, width=2, tags=("fileview", "uiwire"))
                    c.create_oval(x1 - 4, y1 - 4, x1 + 4, y1 + 4, fill=LINKED, outline="", tags=("fileview", "uiwire"))
            except tk.TclError:
                continue
