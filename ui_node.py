"""UI-builder nodes (pure, no Tk).

A UI node is an ordinary function-kind node that also carries its widget tree:

    node["ui"]          the UITree document (see ui_tree.py)
    node["ui_detached"] True after the user chose to edit the code directly

Its `blocks` are DERIVED: one Raw Code block holding the generated source, so
ordering, wires, the Code layer, export and the portable markers all work with
no special cases. While attached, the blocks are rewritten from the tree
whenever it changes; once detached they are the user's to edit and the tree is
kept but no longer drives anything. See docs/ui-builder-design.md.
"""
import re

import ui_gen
from nodes_model import make_node
from ui_tree import UITree

UI_KEY = "ui"
DETACHED_KEY = "ui_detached"


def is_ui_node(node):
    return isinstance(node, dict) and isinstance(node.get(UI_KEY), dict)


def is_detached(node):
    return bool(node.get(DETACHED_KEY))


def make_ui_node(name, node_id, tree, order=None):
    """A fresh UI node around `tree` (a UITree). Blocks are filled by regenerate()."""
    node = make_node(name, node_id=node_id, kind="function", blocks=[], order=order)
    node[UI_KEY] = tree.to_dict()
    return node


def load_tree(node, pack=None):
    """The node's UITree, or None when its document is damaged."""
    try:
        return UITree.from_dict(node[UI_KEY], is_container=pack.is_container if pack else None)
    except (KeyError, ValueError):
        return None


def store_tree(node, tree):
    node[UI_KEY] = tree.to_dict()


def widget_count(node):
    doc = node.get(UI_KEY)
    if not isinstance(doc, dict):
        return 0

    def count(w):
        kids = w.get("children") if isinstance(w, dict) else None
        return 1 + sum(count(k) for k in kids) if isinstance(kids, list) else 1
    return max(0, count(doc.get("root")) - 1)          # the window itself isn't counted


def event_targets(node):
    """Ids of the nodes the UI's events call (handlers and popup windows), in
    the order the widgets appear, each once. [] for a node without a UI."""
    doc = node.get(UI_KEY) if isinstance(node, dict) else None
    out = []

    def walk(w):
        if not isinstance(w, dict):
            return
        events = w.get("events")
        if isinstance(events, dict):
            for target in events.values():
                if isinstance(target, str) and target and target not in out:
                    out.append(target)
        for child in w.get("children") or []:
            walk(child)
    if isinstance(doc, dict):
        walk(doc.get("root"))
    return out


def pack_id_of(node):
    """The id of the UI library a UI node was made for ('python/tkinter'), or None."""
    doc = node.get(UI_KEY) if isinstance(node, dict) else None
    pid = doc.get("pack") if isinstance(doc, dict) else None
    return pid if isinstance(pid, str) and pid else None


def function_name(node):
    """build_<node name> as a valid identifier."""
    slug = re.sub(r"\W+", "_", str(node.get("name") or "ui")).strip("_") or "ui"
    return f"build_{slug}"


def generate_text(node, pack, resolve_handler=None, preview=False):
    """(source text | None, problems). None when the tree is damaged or
    doesn't belong to `pack`."""
    tree = load_tree(node, pack)
    if tree is None:
        return None, ["the UI data is damaged"]
    if tree.pack_id != pack.id:
        return None, [f"this UI was made for '{tree.pack_id}', not '{pack.id}'"]
    if tree.read_only:
        return None, ["this UI was made by a newer Blockliner"]
    result = ui_gen.generate(tree, pack, handler_name=resolve_handler, function_name=function_name(node))
    return ui_gen.render(result, preview=preview), result["problems"]


def preview_source(node, pack, resolve_handler=None):
    """(runnable script | None, problems) to see the UI on its own. Event
    handlers live in other nodes, so each one the UI points at is replaced by
    a stub that just prints its name; nothing else of the project runs.
    Only Python packs can be previewed this way (None otherwise)."""
    if not pack.id.startswith("python/"):
        return None, ["previewing is only available for Python UI packs so far"]
    handlers = []

    def record(target_id):
        name = resolve_handler(target_id) if resolve_handler else None
        if name and name not in handlers:
            handlers.append(name)
        return name
    text, problems = generate_text(node, pack, record, preview=True)
    if text is None:
        return None, problems
    stubs = "".join(f"def {n}(*args, **kwargs):\n    print({n + ' called'!r})\n\n\n" for n in handlers)
    # stubs go after the imports, before the build function
    head, sep, rest = text.partition("\n\ndef ")
    return (head + "\n\n" + stubs + "def " + rest) if sep else (stubs + text), problems


def regenerate(node, pack, raw_block_id, raw_param, resolve_handler=None):
    """Rewrite an attached UI node's blocks from its tree. Returns the
    generator's problems, or None when nothing was done (detached, no Raw Code
    block, no pack, or unusable data)."""
    if is_detached(node) or pack is None or not raw_block_id:
        return None
    text, problems = generate_text(node, pack, resolve_handler)
    if text is None:
        return None
    new_blocks = [(raw_block_id, {raw_param: text.rstrip("\n")})]
    if node.get("blocks") != new_blocks:
        # In place: the app keeps this same list as project_blocks, and a
        # replaced list would be written back over the new code on the next sync.
        if isinstance(node.get("blocks"), list):
            node["blocks"][:] = new_blocks
        else:
            node["blocks"] = new_blocks
    return problems


def matches_code(node, pack, code, resolve_handler=None):
    """True when `code` (a file's text for this node) is exactly what the tree
    generates - i.e. nobody hand-edited it. Whitespace at the ends is ignored."""
    text, _problems = generate_text(node, pack, resolve_handler)
    return text is not None and text.strip() == (code or "").strip()


def detach(node):
    node[DETACHED_KEY] = True


def reattach(node):
    """Back to designer-driven; the caller must regenerate() afterwards,
    which replaces any hand-edited code."""
    node.pop(DETACHED_KEY, None)


def clean_from_json(raw):
    """(ui document | None, detached) from a saved node dict; a damaged
    document is dropped (the node then loads as a plain function node)."""
    doc = raw.get(UI_KEY) if isinstance(raw, dict) else None
    if not isinstance(doc, dict):
        return None, False
    try:
        UITree.from_dict(doc)
    except ValueError:
        return None, False
    return doc, bool(raw.get(DETACHED_KEY))
