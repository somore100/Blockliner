"""What the UI designer needs from the document it edits. No Tk imports.

UIDocumentPort is the interface; CodeBuilderUIPort implements it for the UI
node currently open in Code Builder (through CodeBuilderFacade). The designer
editor depends only on the interface, so a test can give it an in-memory
document instead.
"""
import ui_node


class UIDocumentPort:
    """The document is one UITree plus its UI pack."""

    def key(self):
        """Identity of the document; changes when another one is shown."""
        raise NotImplementedError

    def pack(self):
        raise NotImplementedError

    def stored(self):
        """The tree as last stored (a dict), to tell whether a cached tree is current."""
        raise NotImplementedError

    def load_tree(self):
        raise NotImplementedError

    def store_tree(self, tree):
        raise NotImplementedError

    def handler_targets(self):
        """[(name, id, is_window)] of the functions an event can call."""
        raise NotImplementedError

    def create_handler(self, widget_name, event_key):
        """A new empty handler function; returns its id."""
        raise NotImplementedError

    def detach(self):
        """Hand the generated code over to the user (the designer stops owning it)."""
        raise NotImplementedError

    def preview_source(self):
        """(runnable script | None, problems)."""
        raise NotImplementedError

    def regenerate(self):
        """Bring the generated code up to date with the stored tree."""
        raise NotImplementedError

    def mark_dirty(self):
        raise NotImplementedError


class CodeBuilderUIPort(UIDocumentPort):
    """The UI node open in Code Builder right now (looked up on each call,
    so it follows tab and node switches)."""

    def __init__(self, facade):
        self._cb = facade

    def key(self):
        return id(self._cb.active_node())

    def pack(self):
        return self._cb.ui_pack()

    def stored(self):
        return self._cb.active_node()[ui_node.UI_KEY]

    def load_tree(self):
        node, pack = self._cb.context()
        return ui_node.load_tree(node, pack)

    def store_tree(self, tree):
        ui_node.store_tree(self._cb.active_node(), tree)

    def handler_targets(self):
        return [(n["name"], n["id"], ui_node.is_ui_node(n))
                for n in self._cb.function_nodes(exclude=self._cb.active_node())]

    def create_handler(self, widget_name, event_key):
        return self._cb.add_function_node(f"on_{widget_name}_{event_key}")

    def detach(self):
        ui_node.detach(self._cb.active_node())

    def preview_source(self):
        node, pack = self._cb.context()
        return ui_node.preview_source(node, pack, self._cb.handler_resolver())

    def regenerate(self):
        self._cb.regenerate()

    def mark_dirty(self):
        self._cb.mark_dirty()
