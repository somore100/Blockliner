"""Open several selected nodes together in one Blocks-layer view.

State lives in self._multi = {"tab", "list", "ids"}. While it is active,
self.project_blocks IS the combined list (see multi_open.py). The nodes
themselves are kept current by multi_flush(), which runs at the start of every
refresh_workspace() and in sync_active_tab_state(), i.e. before anything reads
node["blocks"] (code generation, save, export).
"""
import tkinter as tk
from nodes_model import find_node_by_id, function_nodes_in_tree_order
from multi_open import NODE_MARK, build, is_marker, order_nodes, real_count, split
from ui_common import DARK_ACCENT, DARK_BG, DARK_FG, DARK_PANEL

MARKER_COLOR = "#e8a33d"


class NodeMarkerRow(tk.Frame):
    """The separator row that introduces one node inside the combined view.
    Not a BlockWidget: no buttons, nothing to drag or edit. It has an
    `index` so the drop logic can land a block just above it (= at the end
    of the previous node)."""

    def __init__(self, parent, index, node, position, total):
        super().__init__(parent, bg=DARK_BG, highlightthickness=0)
        self.index = index
        self.node_id = node["id"]
        tk.Frame(self, bg=MARKER_COLOR, height=2).pack(fill=tk.X, pady=(6, 3))
        order = node.get("order")
        badge = f"▶{order}" if isinstance(order, int) else "▶?"
        text = f"\U0001F9E9 {node['name']}   {badge}   ({position}/{total})"
        if node.get("ignored"):
            text += "   · ignored"
        if node.get("skipped"):
            text += "   · skipped"
        tk.Label(self, text=text, bg=DARK_BG, fg=MARKER_COLOR,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X, padx=2)


class MultiOpenMixin:

    # ---- state ------------------------------------------------------------
    def multi_state(self):
        return self.__dict__.get("_multi")

    def multi_active(self, tab=None):
        """True while the combined list is what the Blocks layer edits."""
        m = self.multi_state()
        if not m or self.project_blocks is not m["list"]:
            return False
        return tab is None or tab is m["tab"]

    def multi_nodes(self):
        m = self.multi_state()
        if not m:
            return []
        return [n for n in (find_node_by_id(m["tab"]["nodes"], i) for i in m["ids"])
                if n is not None]

    # ---- keeping the nodes current ----------------------------------------
    def multi_flush(self):
        """Write the combined list back into its nodes (in place, so every
        existing reference to a node's block list stays valid)."""
        m = self.multi_state()
        if not m:
            return
        nodes = self.multi_nodes()
        if not nodes:
            return
        parts = split(m["list"], [n["id"] for n in nodes])
        for n in nodes:
            n["blocks"][:] = parts[n["id"]]

    def multi_rebuild(self):
        """Regenerate the combined list from the nodes, in place (so the
        lazy window and project_blocks keep pointing at it). This also
        re-normalizes it: every node gets exactly one marker, in order."""
        m = self.multi_state()
        if not m:
            return
        nodes = self.multi_nodes()
        m["ids"] = [n["id"] for n in nodes]
        m["list"][:] = build(nodes)

    def multi_exit(self):
        """Leave combined mode: flush, then point the editor at the active
        node again."""
        m = self.multi_state()
        if not m:
            return
        if self.project_blocks is m["list"]:
            self.multi_flush()
            self._multi = None
            tab = m["tab"]
            if getattr(self, "tabs", None) and any(t is tab for t in self.tabs):
                self.project_blocks = self.get_active_node(tab)["blocks"]
        else:
            self._multi = None

    def multi_check(self):
        """First thing in refresh_workspace(): either keep the combined list
        in step with its nodes, or drop the state because something else
        took over (another node/tab opened, or we left the Blocks layer)."""
        m = self.multi_state()
        if not m:
            return
        still_here = (self.project_blocks is m["list"] and self.view_mode == "node"
                      and getattr(self, "tabs", None)
                      and m["tab"] is self.tabs[self.active_tab_index])
        if still_here:
            self.multi_flush()
            self.multi_rebuild()
            if len(self.multi_nodes()) < 2:
                self.multi_exit()
        else:
            self.multi_exit()

    def block_number_at(self, index):
        """1-based number of the block at `index` in the combined list,
        not counting separator rows."""
        return real_count(self.project_blocks[:index + 1])

    def real_block_count(self):
        if self.multi_active():
            return real_count(self.project_blocks)
        return len(self.project_blocks)

    # ---- opening ------------------------------------------------------------
    def selected_function_nodes(self):
        tab = self.tabs[self.active_tab_index]
        sel = self.selected_nodes()
        return [n for n in function_nodes_in_tree_order(tab["nodes"]) if n["id"] in sel]

    def open_selected_nodes(self):
        """Open every selected function node in ONE Blocks view, in run
        order. With fewer than two, it is a plain open."""
        tab = self.tabs[self.active_tab_index]
        nodes = order_nodes(self.selected_function_nodes())
        if not nodes:
            return
        if len(nodes) == 1:
            self.open_node(nodes[0]["id"])
            return
        self.sync_active_tab_state()         # also flushes an earlier combined view
        self._multi = None
        combined = build(nodes)
        self._multi = {"tab": tab, "list": combined, "ids": [n["id"] for n in nodes]}
        tab["active_node_id"] = nodes[0]["id"]
        self.project_blocks = combined
        self.view_mode = "node"
        self.selected_nodes().clear()
        self.refresh_workspace()
        self.refresh_tab_bar()

    def open_together_label(self):
        n = len(self.selected_function_nodes())
        return f"Open {n} selected together"

    # ---- UI bits --------------------------------------------------------------
    def multi_crumb(self):
        """Breadcrumb tail for the nav bar while combined, else None."""
        if not self.multi_active():
            return None
        return f"\U0001F9E9 {len(self.multi_nodes())} nodes together"

    def make_node_marker_row(self, index):
        node = find_node_by_id(self.multi_state()["tab"]["nodes"],
                               self.project_blocks[index][1].get("node_id"))
        if node is None:
            return None
        nodes = self.multi_nodes()
        pos = next((i for i, n in enumerate(nodes) if n is node), 0) + 1
        return NodeMarkerRow(self.workspace_frame, index, node, pos, len(nodes))
