"""Pure test: making an ordinary node a function (node_function.py)."""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import node_function as nf
import node_ports
from nodes_model import make_node, sorted_function_nodes

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def render(blocks, indent=""):
    """Tiny Python renderer for the handful of block kinds used here."""
    out = []
    for bid, p in blocks:
        if bid == "assign_variable":
            out.append(f"{indent}{p['variable']} = {p['value']}")
        elif bid == "print_output":
            out.append(f"{indent}print({p['value']})")
        elif bid == "node_output":
            out.append(f"{indent}{p['name']} = {p['value']}")
        elif bid == "node_input":
            out.append(f"{indent}# needs {p['name']}")
        elif bid == "return_statement":
            out.append(f"{indent}return {p['value']}")
        elif bid == "func_def":
            out.append(f"{indent}def {p['name']}({p['params']}):")
            out += render(p["_children"], indent + "    ").split("\n") if p["_children"] else [indent + "    pass"]
    return "\n".join(out)


def program(nodes):
    return "\n".join(render(n["blocks"]) for n in sorted_function_nodes(nodes))


def run(code):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<t>", "exec"), {})
    return out.getvalue().split()


def build():
    maker = make_node("maker", node_id="m", order=1, blocks=[
        ("node_input", {"name": "base"}), ("assign_variable", {"variable": "raw", "value": "base + 'bc'"}),
        ("node_output", {"name": "text", "value": "raw.upper()"})])
    start = make_node("start", node_id="s", order=0, blocks=[("assign_variable", {"variable": "base", "value": "'a'"})])
    taker = make_node("taker", node_id="t", order=2, blocks=[("print_output", {"value": "text"})])
    again = make_node("again", node_id="u", order=3, blocks=[("print_output", {"value": "text + '!'"})])
    return [start, maker, taker, again]


nodes = build()
before = run(program(nodes) + "\n" + "")
check("before: the program prints what the node published", before == ["ABC", "ABC!"])

maker = nodes[1]
check("an ordinary node with blocks can be made a function", nf.why_not(maker, "python") is None)
check("other languages are refused with a reason", "Python" in nf.why_not(maker, "c"))
check("an empty node is refused", nf.why_not(make_node("e"), "python") is not None)
info = nf.make_function(nodes, maker)
check("the node is now a function node named like itself", node_ports.has_function(maker) and nf.make_function.__name__)
check("it reports parameters and returned names", info["inputs"] == ["base"] and info["outputs"] == ["text"] and info["name"] == "maker")
fd = maker["blocks"][0][1]
check("the Node Input became a parameter", fd["params"] == "base")
check("the Node Output became an assignment, followed by a return of its name",
      fd["_children"][-2] == ("assign_variable", {"variable": "text", "value": "raw.upper()"})
      and fd["_children"][-1] == ("return_statement", {"value": "text"}))
check("the Node Input block is gone from the body", not any(b[0] == "node_input" for b in fd["_children"]))
check("its ports are the same names as before", node_ports.node_interface(maker) == (["base"], ["text"]))
check("the first node that used the output now calls the function", info["caller"] == "taker"
      and nodes[2]["blocks"][0] == ("assign_variable", {"variable": "text", "value": "maker(base)"}))
check("the later user did not get a second call", nodes[3]["blocks"] == [("print_output", {"value": "text + '!'"})])
check("the function is a pure function node, so it is written first", sorted_function_nodes(nodes)[0] is maker)
after = run(program(nodes))
check("the program does the same thing as before", after == before)

# no declared outputs: the assigned variables are returned
n2 = make_node("calc", node_id="c", order=1, blocks=[("assign_variable", {"variable": "a", "value": "1"}),
                                                     ("assign_variable", {"variable": "b", "value": "2"})])
reader = make_node("show", node_id="r", order=2, blocks=[("print_output", {"value": "a + b"})])
info2 = nf.make_function([n2, reader], n2)
check("without declared outputs the assigned variables are returned", info2["outputs"] == ["a", "b"]
      and n2["blocks"][0][1]["_children"][-1] == ("return_statement", {"value": "a, b"}))
check("and the user unpacks them", reader["blocks"][0] == ("assign_variable", {"variable": "a, b", "value": "calc()"}))
check("that program still prints 3", run(program([n2, reader])) == ["3"])

# a node with nobody using its output: no call is added
lone = make_node("lone", node_id="l", order=1, blocks=[("node_output", {"name": "x", "value": "1"})])
info3 = nf.make_function([lone], lone)
check("with no users there is no caller", info3["caller"] is None)

# names that are not valid function names
odd = make_node("Node 2", node_id="o", blocks=[("print_output", {"value": "1"})])
other = make_node("Node_2", node_id="p", blocks=[("print_output", {"value": "2"})])
info4 = nf.make_function([odd, other], odd)
check("a name with a space is fixed and made unique", info4["renamed"] and info4["name"] == "Node_2_2" and odd["name"] == "Node_2_2")
check("a name starting with a digit gets a prefix", nf.function_name([], make_node("2fast")) == "node_2fast")

# a user that is itself a function node needs a hand-made call
src = make_node("src", node_id="a", order=1, blocks=[("node_output", {"name": "v", "value": "5"})])
fnuser = make_node("fnuser", node_id="b", order=2, blocks=[("func_def", {"name": "fnuser", "params": "", "_children": [
    ("print_output", {"value": "v"})]}), ("print_output", {"value": "v"})])    # also runs code, so it is not hoisted
info5 = nf.make_function([src, fnuser], src)
check("a function that used the output is reported, not edited", info5["by_hand"] == ["fnuser"] and info5["caller"] is None)
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
