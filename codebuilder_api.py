"""The part of Code Builder the UI designer is allowed to use.

The designer reads and changes one function node of the open file. It goes
through this class instead of reaching into the app's tab list, so Code
Builder's internals can change without touching the designer, and a test can
check that it doesn't look inside. No Tk imports here.
"""
import re
import uuid

from nodes_model import make_node, next_order


class CodeBuilderFacade:
    def __init__(self, app):
        self._app = app

    # ---- where we are -------------------------------------------------------
    def available(self):
        return bool(getattr(self._app, "tabs", None))

    def in_node_view(self):
        return getattr(self._app, "view_mode", None) == "node"

    def _tab(self):
        return self._app.tabs[self._app.active_tab_index]

    def language(self):
        return self._tab()["language"]

    def active_node(self):
        """The node open in the editor (a function node)."""
        return self._app.get_active_node(self._tab())

    def ui_pack(self):
        """The UI pack for the open file's language, or None."""
        return self._app.ui_pack_for(self.language())

    def context(self):
        """(node, pack) of the open node."""
        return self.active_node(), self.ui_pack()

    # ---- other nodes ----------------------------------------------------------
    def function_nodes(self, exclude=None):
        """Function-kind nodes of the open file (any depth), except `exclude`."""
        return [n for n, _p in self._app.iter_tab_nodes(self._tab())
                if n.get("kind", "function") == "function" and n is not exclude]

    def add_function_node(self, base_name):
        """Add an empty function node named after `base_name` (made unique and
        a valid identifier) next to the others; returns its id."""
        tab = self._tab()
        taken = {n["name"] for n, _p in self._app.iter_tab_nodes(tab)}
        base = re.sub(r"\W+", "_", base_name).strip("_")
        name, i = base, 2
        while name in taken:
            name, i = f"{base}_{i}", i + 1
        node = make_node(name, node_id=str(uuid.uuid4())[:8], kind="function", blocks=[],
                         order=next_order(tab["nodes"]))
        tab["nodes"].append(node)
        return node["id"]

    # ---- code -----------------------------------------------------------------
    def handler_resolver(self):
        """id -> the function name an event handler id stands for (or None)."""
        return self._app._ui_handler_resolver(self._tab())

    def raw_code_text(self, node):
        """The node's code as one text, or None unless it is only raw-code blocks."""
        raw_id = self._app.get_raw_code_block_id(self.language())
        if not raw_id or not node.get("blocks"):
            return None
        param = self._app.get_raw_code_param_name(raw_id)
        if any(b != raw_id for b, _p in node["blocks"]):
            return None
        return "\n".join(str(p.get(param, "")) for _b, p in node["blocks"])

    def regenerate(self):
        """Rewrite the generated code of attached UI nodes and show it."""
        self._app.regenerate_ui_nodes()
        self._app.update_generated_code()

    def forget_generated(self, node):
        """Drop what was remembered about the node's last generated code
        (after the designer takes a node back)."""
        self._app.__dict__.setdefault("_ui_last_blocks", {}).pop((id(self._tab()), node["id"]), None)

    # ---- state ------------------------------------------------------------------
    def mark_dirty(self):
        self._app.mark_active_tab_dirty()
