"""Pure test: function nodes are written before the code that calls them, and a wire to a plain
node is a run-order change (nodes_model.is_pure_function_node / sorted_function_nodes / run_after)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nodes_model as nm
from nodes_model import make_node, sorted_function_nodes

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def fdef(name):
    return ("func_def", {"name": name, "params": "", "_children": [("return_statement", {"value": "1"})]})


def names(nodes):
    return [n["name"] for n in sorted_function_nodes(nodes)]


greet = make_node("greet", node_id="g", blocks=[fdef("greet")], order=2)
main = make_node("main", node_id="m", blocks=[("assign_variable", {"variable": "msg", "value": "greet()"})], order=1)
check("a node that only defines its own function is a pure function node", nm.is_pure_function_node(greet))
check("plus comments and imports is still pure", nm.is_pure_function_node(
    make_node("greet", blocks=[("comment", {"text": "x"}), ("import_module", {"module": "os"}), fdef("greet")])))
check("a function named differently is not 'its' function", not nm.is_pure_function_node(make_node("other", blocks=[fdef("greet")])))
check("other code in the node makes it a normal node", not nm.is_pure_function_node(
    make_node("greet", blocks=[fdef("greet"), ("print_output", {"value": "1"})])))
check("an empty node is not a function node", not nm.is_pure_function_node(make_node("x", blocks=[])))

check("the function is written before its caller although it has the later number", names([main, greet]) == ["greet", "main"])
check("with no function nodes the old order is unchanged", names([
    make_node("a", node_id="a", blocks=[("print_output", {"value": "1"})], order=2),
    make_node("b", node_id="b", blocks=[("print_output", {"value": "2"})], order=1)]) == ["b", "a"])
two = [make_node("f2", blocks=[fdef("f2")], order=5), make_node("f1", blocks=[fdef("f1")], order=3), main]
check("function nodes keep their own order among themselves", names(two) == ["f1", "f2", "main"])
unassigned = make_node("late", node_id="l", blocks=[fdef("late")])
unassigned["order"] = None
check("an unassigned function node is still written first", names([main, unassigned]) == ["late", "main"])

# run_after
a, b, c = (make_node(n, node_id=n, blocks=[("print_output", {"value": "1"})], order=i) for i, n in enumerate("abc", 1))
nodes = [a, b, c]
check("run_after puts the node right after the anchor", nm.run_after(nodes, c, a) and [n["name"] for n in sorted_function_nodes(nodes)] == ["a", "c", "b"])
check("and the numbers stay distinct", len({n["order"] for n in nodes}) == 3)
a2, b2 = make_node("a", node_id="a", blocks=[("print_output", {"value": "1"})]), make_node("b", node_id="b", blocks=[("print_output", {"value": "1"})])
a2["order"] = None
check("an anchor that is not set to run refuses", nm.run_after([a2, b2], b2, a2) is False)
check("a node cannot follow itself", nm.run_after([a], a, a) is False)
legacy = [make_node("x", node_id="x"), make_node("y", node_id="y"), make_node("z", node_id="z")]
check("old nodes without numbers get numbered first", nm.run_after(legacy, legacy[2], legacy[0])
      and [n["name"] for n in sorted_function_nodes(legacy)] == ["x", "z", "y"])
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
