"""Make an ordinary node into a function node (pure, no Tk).

The node's Node Input blocks become the parameters of a Define Function named like the node, its Node
Output blocks (or, when it declares none, the variables it assigns) become what it returns, and
everything else becomes the function's body. Nodes that used its outputs get a call, so the program keeps
doing the same thing. Python only for now (other languages need typed parameters).
"""
import keyword
import re

import node_ports
from nodes_model import function_nodes_in_tree_order, sorted_function_nodes


def why_not(node, language):
    """None when the node can be made a function, else a plain-language reason."""
    if language != "python":
        return "This is only available for Python so far. In other languages, add a Define Function block yourself."
    if node.get("kind", "function") != "function":
        return "Only an ordinary node can become a function."
    if node.get("ui") and not node.get("ui_detached"):
        return "This node's code comes from the UI designer."
    if node_ports.has_function(node):
        return "This node is already a function."
    if not node.get("blocks"):
        return "This node has no blocks yet."
    return None


def function_name(nodes, node):
    """A valid, unused function name for the node: its own name when that already works."""
    base = re.sub(r"\W+", "_", (node.get("name") or "").strip()).strip("_") or "node_function"
    if base[0].isdigit() or keyword.iskeyword(base):
        base = f"node_{base}"
    taken = {(n.get("name") or "").strip() for n in function_nodes_in_tree_order(nodes) if n is not node}
    name, i = base, 2
    while name in taken:
        name, i = f"{base}_{i}", i + 1
    return name


def make_function(nodes, node):
    """Turn `node` (of the node list `nodes`) into a function node in place.
    Returns {"name", "renamed", "inputs", "outputs", "caller", "by_hand"}: the function name, whether the
    node was renamed, its parameters and returned names, the node that now calls it (or None) and the
    nodes that use its outputs but are functions themselves (they need a call added by hand)."""
    inputs = node_ports.declared_names(node, "node_input")
    outputs = list(node_ports.node_interface(node)[1])
    name = function_name(nodes, node)

    # who used the outputs, found before the blocks change
    users = {}
    live = sorted_function_nodes(nodes)
    for producer, user, names in node_ports.data_wires(live):
        if producer == node["id"]:
            users[user] = names
    ordered = [n for n in live if n["id"] in users]
    caller = next((n for n in ordered if not node_ports.has_function(n)), None)
    by_hand = [n.get("name") or n["id"] for n in ordered if node_ports.has_function(n)]

    body = []
    for entry in node.get("blocks") or []:
        block_id, params = entry
        if block_id == "node_input":
            continue
        if block_id == "node_output" and isinstance(params, dict):
            body.append(("assign_variable", {"variable": params.get("name", ""), "value": params.get("value", "")}))
        else:
            body.append(entry)
    if outputs:
        body.append(("return_statement", {"value": ", ".join(outputs)}))

    renamed = node.get("name") != name
    node["name"] = name
    node["blocks"][:] = [("func_def", {"name": name, "params": ", ".join(inputs), "_children": body})]

    if caller is not None and outputs:
        call = ("assign_variable", {"variable": ", ".join(outputs), "value": f"{name}({', '.join(inputs)})"})
        if call not in caller["blocks"]:
            caller["blocks"].insert(0, call)
    return {"name": name, "renamed": renamed, "inputs": inputs, "outputs": outputs,
            "caller": (caller.get("name") or caller["id"]) if caller is not None and outputs else None,
            "by_hand": by_hand}
