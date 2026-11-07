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


def range_between(anchor, index):
    """Shift+click: every index from the anchor to the clicked one, both included."""
    lo, hi = sorted((anchor, index))
    return set(range(lo, hi + 1))


def pick(current, index, anchor, ctrl, shift):
    """The selection after a click on block `index` (top-level list).
    Ctrl toggles it, Shift extends from the anchor, a plain click selects only it.
    Returns (selection set, new anchor)."""
    if shift and anchor is not None:
        return range_between(anchor, index), anchor
    if ctrl:
        chosen = set(current)
        if anchor is not None and not chosen:
            chosen.add(anchor)                     # the block selected by an earlier plain click counts
        chosen ^= {index}
        return chosen, index
    return {index}, index
