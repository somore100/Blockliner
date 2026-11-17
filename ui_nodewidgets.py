"""Widgets on the Nodes layer: a UI window's box can open up to list its widgets, each with a dot for every event it
has. A filled dot is linked to a function node (the wire starts at that dot, click the name to open the function), an
empty dot makes a new function and links it. Clicking a widget's name opens the window in the designer with that
widget selected. The function's own box says which widget event runs it. The pure part is ui_node.widget_rows."""
import tkinter as tk
import uuid

import ui_node
from canvas_view import NODE_W
from nodes_model import find_node_by_id, make_node, next_order
from ui_common import BLOCK_BG

LINKED = "#4ec9b0"
FREE = "#777777"
ROW_LIMIT = 30                       # a window with more widgets shows the first ones and a count


class NodeWidgetsMixin:

    def _ui_tab(self):
        return self.tabs[self.active_tab_index]

    def _ui_lookup(self):
        tab = self._ui_tab()
        return lambda i: find_node_by_id(tab["nodes"], i)

    def _ui_pack_of(self, node):
        return self.ui_pack_for(self._ui_tab()["language"], ui_node.pack_id_of(node))

    def toggle_ui_widgets(self, nid):
        node = find_node_by_id(self._ui_tab()["nodes"], nid)
        if node is None:
            return
        if node.get("ui_open"):
            node.pop("ui_open", None)
        else:
            node["ui_open"] = True
        self.mark_active_tab_dirty()
        if not self.refresh_nodes_in_place(rebuild_ids=(nid,)):
            self.refresh_workspace()

    # ---- the rows inside a UI node's box -------------------------------------
    def build_ui_widget_rows(self, box, node, font, pad):
        """Pack the widget list into `box` and remember where each linked event's dot is, for the wires."""
        ports = self.__dict__.setdefault("_ui_ports", {})
        ports[node["id"]] = []
        rows = ui_node.widget_rows(node, self._ui_pack_of(node), self._ui_lookup())
        holder = tk.Frame(box, bg=BLOCK_BG)
        holder.pack(fill=tk.X, padx=10, pady=(0, 8))
        if not rows:
            tk.Label(holder, text="No widgets yet: open the window and add some.", bg=BLOCK_BG, fg="#888888",
                     font=font(8), anchor="w").pack(fill=tk.X)
            return
        for row in rows[:ROW_LIMIT]:
            line = tk.Frame(holder, bg=BLOCK_BG)
            line.pack(fill=tk.X, pady=1)
            mark = "▣" if row["screen"] else "▫"
            name = tk.Label(line, text=f"{mark} {row['name']}", bg=BLOCK_BG, fg="#dddddd", font=font(9), anchor="w",
                            cursor="hand2")
            name.pack(side=tk.LEFT, padx=(row["depth"] * 12, 0))
            name.bind("<Button-1>", lambda _e, nid=node["id"], wid=row["id"]: self.open_ui_widget(nid, wid))
            tk.Label(line, text=row["label"], bg=BLOCK_BG, fg="#777777", font=font(7)).pack(side=tk.LEFT, padx=(4, 0))
            for ev in reversed(row["events"]):
                linked = bool(ev["handler"])
                text = f"{ev['label']} → {ev['handler']['name']}" if linked else (
                    f"{ev['label']} → (missing)" if ev["handler_id"] else f"{ev['label']} +")
                lab = tk.Label(line, text=text + (" ●" if linked else " ○"), bg=BLOCK_BG,
                               fg=LINKED if linked else FREE, font=font(8), cursor="hand2", anchor="e")
                lab.pack(side=tk.RIGHT, padx=(6, 0))
                if linked:
                    lab.bind("<Button-1>", lambda _e, h=ev["handler_id"]: self.open_node(h))
                    ports[node["id"]].append((lab, ev["handler_id"]))
                elif not ev["handler_id"]:
                    lab.bind("<Button-1>", lambda _e, nid=node["id"], wid=row["id"], key=ev["key"]:
                             self.link_new_ui_handler(nid, wid, key))
        if len(rows) > ROW_LIMIT:
            tk.Label(holder, text=f"+ {len(rows) - ROW_LIMIT} more widgets", bg=BLOCK_BG, fg="#888888",
                     font=font(8), anchor="w").pack(fill=tk.X)

    def ui_port_offsets(self, source_id, target_id):
        """Pixel offsets (from the top of the box) of the dots that link source_id's widgets to target_id."""
        entry = self.__dict__.get("_ui_ports", {}).get(source_id)
        shown = self.__dict__.get("_fileview_boxes", {}).get(source_id)
        if not entry or shown is None:
            return []
        box = shown[1]
        box.update_idletasks()
        out = []
        for lab, hid in entry:
            if hid == target_id:
                try:
                    out.append(lab.winfo_rooty() - box.winfo_rooty() + lab.winfo_height() / 2)
                except tk.TclError:
                    pass
        return out

    # ---- clicks -------------------------------------------------------------
    def open_ui_widget(self, ui_id, widget_id):
        """Open the window in the designer with this widget selected."""
        node = find_node_by_id(self._ui_tab()["nodes"], ui_id)
        if node is not None and not ui_node.is_detached(node):
            self._ui_pending_sel = widget_id
        self.open_node(ui_id)

    def link_new_ui_handler(self, ui_id, widget_id, event_key):
        """Make an empty function (on_<widget>_<event>) next to the window and link the widget's event to it."""
        tab = self._ui_tab()
        node = find_node_by_id(tab["nodes"], ui_id)
        pack = self._ui_pack_of(node) if node else None
        tree = ui_node.load_tree(node, pack) if node else None
        widget = tree.find(widget_id) if tree else None
        if widget is None:
            return None
        taken = {n["name"] for n, _p in self.iter_tab_nodes(tab)}
        base = ui_node.handler_base_name(widget["name"], event_key)
        name, i = base, 2
        while name in taken:
            name, i = f"{base}_{i}", i + 1
        handler = make_node(name, node_id=str(uuid.uuid4())[:8], kind="function", blocks=[], order=next_order(tab["nodes"]))
        placed = len(ui_node.event_targets(node))
        handler["canvas_x"] = node.get("canvas_x", 30) + (node.get("canvas_w") or NODE_W) + 120
        handler["canvas_y"] = node.get("canvas_y", 20) + 20 + 130 * placed
        self._ui_container_list(tab, ui_id).append(handler)
        tree.set_event(widget_id, event_key, handler["id"])
        ui_node.store_tree(node, tree)
        self.mark_active_tab_dirty()
        self.refresh_workspace()
        return handler["id"]

    def _ui_container_list(self, tab, nid):
        def search(nodes):
            for n in nodes:
                if n["id"] == nid:
                    return nodes
                found = search(n.get("child_nodes", []))
                if found is not None:
                    return found
            return None
        return search(tab["nodes"]) or tab["nodes"]

    # ---- the other direction: which widget runs this function ----------------------
    def ui_triggers_text(self, node_id):
        """'<- window.widget · On click' lines (a few) for the box of a function that widget events run, or ''."""
        tab = self._ui_tab()
        windows = [n for n, _p in self.iter_tab_nodes(tab) if ui_node.is_ui_node(n)]
        if not windows:
            return ""
        found = ui_node.triggers_for(windows, node_id, self._ui_pack_of, self._ui_lookup())
        if not found:
            return ""
        lines = [f"← {w}.{wd} · {ev}" for w, wd, ev in found[:2]]
        if len(found) > 2:
            lines.append(f"← +{len(found) - 2} more")
        return "\n".join(lines)
