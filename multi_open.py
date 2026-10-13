"""Pure logic for "Open together": several nodes shown as ONE block list.

The Blocks layer edits a single flat list (`app.project_blocks`). To show
several nodes at once, their blocks are concatenated into one combined list
and each node's segment is introduced by a separator ("marker") entry:

    [marker A, a1, a2, marker B, b1, marker C, c1, c2]

Ownership is purely positional - a block belongs to the nearest marker above
it. That makes every ordinary edit work unchanged on the combined list:
edit (the tuple is replaced), insert, delete, up/down and drag-reorder; moving
a block across a marker simply moves it to the neighbouring node. Markers
never reach a node: `split()` strips them before the blocks are written back.

No Tk in here (tests/test_multi_open.py covers it headless).
"""

NODE_MARK = "__node__"


def is_marker(entry):
    try:
        return len(entry) == 2 and entry[0] == NODE_MARK
    except TypeError:
        return False


def make_marker(node_id):
    return (NODE_MARK, {"node_id": node_id})


def marker_node_id(entry):
    params = entry[1]
    return params.get("node_id") if isinstance(params, dict) else None


def order_nodes(nodes):
    """The nodes in run order: by their order number, ties by the given
    (tree) order; no order key = at its position; explicit None = last.
    Same rule as nodes_model.sorted_function_nodes, but WITHOUT dropping
    ignored nodes - the user opened them on purpose."""
    def key(pair):
        idx, n = pair
        if "order" not in n:
            return (0, idx + 1, idx)
        if n["order"] is None:
            return (1, 0, idx)
        return (0, n["order"], idx)
    return [n for _i, n in sorted(enumerate(nodes), key=key)]


def build(nodes):
    """Combined list for these nodes (already in display order)."""
    combined = []
    for node in nodes:
        combined.append(make_marker(node["id"]))
        combined.extend(node["blocks"])
    return combined


def split(combined, node_ids):
    """{node_id: [blocks]} from a combined list. Blocks before the first
    marker go to the first node (something was dragged above it); a marker
    for an id that is not one of ours is ignored; a node whose marker is
    gone ends up empty."""
    result = {nid: [] for nid in node_ids}
    current = node_ids[0] if node_ids else None
    for entry in combined:
        if is_marker(entry):
            nid = marker_node_id(entry)
            if nid in result:
                current = nid
            continue
        if current is not None:
            result[current].append(entry)
    return result


def real_count(combined):
    return sum(1 for e in combined if not is_marker(e))
