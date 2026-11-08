"""Pure logic (no Tk) for "make a node from the selected blocks".

A node is a chunk of the file's code that runs in a set order, so pulling blocks
out of the middle of one must not change what runs when. The selected blocks
become one new node that runs right after the one they came from. Blocks that
sat AFTER the last selected one move into a second new node that runs after
that, so they still run last. Unselected blocks between selected ones stay put.
"""
from nodes_model import function_nodes_in_tree_order, normalize_orders


def split_blocks(blocks, selected):
    """(kept, taken, tail): the blocks staying in the node, the selected ones
    (in their order), and the unselected ones after the last selected block."""
    chosen = sorted({i for i in selected if 0 <= i < len(blocks)})
    if not chosen:
        return list(blocks), [], []
    last = chosen[-1]
    pick = set(chosen)
    kept = [b for i, b in enumerate(blocks) if i not in pick and i < last]
    taken = [blocks[i] for i in chosen]
    tail = [b for i, b in enumerate(blocks) if i > last]
    return kept, taken, tail


def find_parent_list(nodes, node_id):
    """The list (the tab's node list, or a class/category's child_nodes) that holds the node."""
    for n in nodes:
        if n["id"] == node_id:
            return nodes
        found = find_parent_list(n.get("child_nodes") or [], node_id)
        if found is not None:
            return found
    return None


def place_after(all_nodes, original, new_nodes):
    """Put new_nodes right after `original` in its list and in the run order,
    and give them a spot on the Nodes canvas next to it."""
    parent = find_parent_list(all_nodes, original["id"])
    if parent is None:
        raise ValueError("the node is not in this file")
    normalize_orders(all_nodes)
    base = original.get("order")
    if isinstance(base, int):
        for n in function_nodes_in_tree_order(all_nodes):
            if isinstance(n.get("order"), int) and n["order"] > base:
                n["order"] += len(new_nodes)
        for step, n in enumerate(new_nodes, 1):
            n["order"] = base + step
    else:                                          # an unassigned node: its pieces stay unassigned
        for n in new_nodes:
            n["order"] = None
    at = next(i for i, n in enumerate(parent) if n["id"] == original["id"]) + 1
    parent[at:at] = new_nodes
    if "canvas_x" in original and "canvas_y" in original:
        for step, n in enumerate(new_nodes, 1):
            n["canvas_x"], n["canvas_y"] = original["canvas_x"] + 40 * step, original["canvas_y"] + 60 * step


SELECT_MODE_CHOICES = [
    ("shift", "Shift+click the first and last block (can pick several sections)"),
    ("single", "Click each block you want"),
    ("range", "Click the first block, then the last"),
]


def normalize_select_mode(value):
    return value if value in ("shift", "single", "range") else "shift"


def range_between(anchor, index):
    """Every index from one block to another, both included."""
    lo, hi = sorted((anchor, index))
    return set(range(lo, hi + 1))


def click(selection, index, pending, ctrl, shift, mode="shift"):
    """The selection after a click on block `index` of the top-level list.

    selection: set of picked indices (a lone selected block counts). pending: the block a
    range is waiting to start from, or None. Returns (selection, pending).

    shift  (default) - a plain click picks only that block. Shift+click on a block that is not
                       picked starts a section there; the next Shift+click on an unpicked block
                       picks everything from the start to it, and adds it to what was already
                       picked, so several sections can be built. Shift+click on a picked block
                       drops it. Ctrl+click toggles one block.
    single           - every click toggles that one block.
    range            - the first click picks the block, the second picks everything between the
                       two; a third starts over. Ctrl+click still toggles one block.
    """
    chosen = set(selection)
    if mode == "single":
        return chosen ^ {index}, None
    if ctrl:
        return chosen ^ {index}, None
    if mode == "range":
        if pending is not None and pending != index:
            return range_between(pending, index), None
        if pending == index:
            return set(), None
        return {index}, index
    if not shift:
        return {index}, index
    if index in chosen:
        chosen.discard(index)
        return chosen, None
    if pending is not None:
        return chosen | range_between(pending, index), None
    chosen.add(index)
    return chosen, index
