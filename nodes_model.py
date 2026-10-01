"""Pure node-tree helpers (no Tk): node dicts, lookup, execution order."""



def make_node(name, node_id=None, blocks=None, category=None,
              kind="function", child_nodes=None, locked=False, node_type_id=None,
              order=None):
    """
    A UI-level node: a named container holding one block list, shaped
    EXACTLY like the block lists ui.py has always worked with - a list
    of (block_id, params_dict) tuples, with a container's children
    living in params["_children"] (never a separate .children
    attribute). This is deliberately NOT engine.model.Node's shape
    (BlockInstance objects with a separate .children list) - that
    class was tested in isolation against engine/renderer.py, which
    the live UI's BlockWidget/render_block_list never actually calls.
    Reconciling the two representations is a later (likely
    persistence-related) task, not this one.

    Phase B1: every tab gets exactly one node (name="main"), so this
    is purely an added layer - nothing about what's on screen changes
    yet. Phase B2 is what lets a file hold more than one.

    Phase B3 adds `kind`: "function" (default, has `blocks`) or
    "class" (has `child_nodes` instead - other nodes, not blocks).
    Phase D adds a third kind, "category": a pure visual folder with
    zero codegen effect (also has `child_nodes`, `blocks` always
    empty) - it's just a canvas organizational grouping, invisible to
    generated code. Class is the opposite of category - a real
    code-generation construct whose children render wrapped in
    `class Foo { ... }`. The two are deliberately kept separate:
    category changes editor organization, class changes generated
    code. For now class exists narrowly to make C#/Java's
    auto-created entry point compile (it can't sit outside a class),
    with room left for real OOP semantics later.

    `locked` marks a node as not user-deletable (auto-created entry
    points/wrapping classes) - there's no delete-node feature yet to
    actually enforce this against, but it's set now so that feature
    can honor it from day one instead of needing every entry-point
    node retrofitted later. `node_type_id` ties a node back to the
    node_types.json entry that caused it to be auto-created, if any
    (e.g. "start"), so ensure_entry_point-style logic can recognize
    one already exists instead of creating a duplicate.
    """
    node = {
        "id": node_id or "main",
        "name": name,
        "category": category,
        "kind": kind,
        "blocks": blocks if blocks is not None else [],
        "child_nodes": child_nodes if child_nodes is not None else [],
        "locked": locked,
        "node_type_id": node_type_id,
        # Phase C1: which other nodes (by id) this node's func_call
        # blocks resolve to - always fully recomputed by
        # recompute_references(), never hand-authored or edited
        # directly. Wires are drawn from this, never the reverse.
        "references": [],
    }
    # Execution order (function-kind nodes only): the position this
    # node's blocks take in the generated file. The key is left OUT
    # unless given - an absent key means "legacy/untouched, fill me in
    # by tree position" (see normalize_orders), while an explicit None
    # means "deliberately unassigned" (shown red, generated last).
    if order is not None:
        node["order"] = order
    return node


def find_node_by_id(nodes, node_id):
    """Search a node list (and any class node's child_nodes, at any
    depth) for a node with the given id."""
    for node in nodes:
        if node["id"] == node_id:
            return node
        if node.get("child_nodes"):
            found = find_node_by_id(node["child_nodes"], node_id)
            if found:
                return found
    return None


def function_nodes_in_tree_order(nodes):
    """Every function-kind node (classes/categories hold no blocks, so
    they have no execution order), depth-first in tree order."""
    out = []
    for node in nodes:
        if node.get("kind", "function") == "function":
            out.append(node)
        if node.get("child_nodes"):
            out.extend(function_nodes_in_tree_order(node["child_nodes"]))
    return out


def sorted_function_nodes(nodes):
    """Function-kind nodes in EXECUTION order: by their order number,
    ties broken by tree position; a node with no order key at all is
    treated as sitting at its tree position (so untouched legacy data
    generates exactly as before); explicitly unassigned (None) nodes go
    last - still generated, so no code is ever silently dropped."""
    fn = function_nodes_in_tree_order(nodes)

    def key(pair):
        idx, n = pair
        if "order" not in n:
            return (0, idx + 1, idx)
        if n["order"] is None:
            return (1, 0, idx)
        return (0, n["order"], idx)

    return [n for _i, n in sorted(enumerate(fn), key=key)]


def normalize_orders(nodes):
    """Give every function-kind node that has no order key yet the next
    free number, in tree order (so an untouched file keeps today's
    order, entry point first). Never touches an explicit None
    (unassigned) or an existing number. Returns True if it changed
    anything. Idempotent."""
    fn = function_nodes_in_tree_order(nodes)
    taken = [n["order"] for n in fn if isinstance(n.get("order"), int)]
    nxt = (max(taken) if taken else 0) + 1
    changed = False
    for n in fn:
        if "order" not in n:
            n["order"] = nxt
            nxt += 1
            changed = True
    return changed


def next_order(nodes):
    """The number a newly added function node should get."""
    taken = [n["order"] for n in function_nodes_in_tree_order(nodes)
             if isinstance(n.get("order"), int)]
    return (max(taken) if taken else 0) + 1


def default_active_node_id(nodes):
    """The node a brand-new tab should open into: the first
    function-kind node, searching into class nodes' child_nodes since
    a class itself has no blocks to edit (e.g. for C#/Java, this finds
    the Main/main method nested inside the auto-created wrapping
    class, not the class itself)."""
    for node in nodes:
        if node.get("kind", "function") == "function":
            return node["id"]
        if node.get("child_nodes"):
            found = default_active_node_id(node["child_nodes"])
            if found:
                return found
    return nodes[0]["id"] if nodes else None
