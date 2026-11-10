"""Pure test: Node Input / Node Output blocks declare a node's ports, and the data wires follow them
(node_ports.declared_names / node_interface / data_wires)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import node_ports as np_
from engine import loader
from engine.renderer import with_generate_code
from nodes_model import make_node

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def out(name, value=""):
    return ("node_output", {"name": name, "value": value})


def inp(name):
    return ("node_input", {"name": name})


def setv(name, value):
    return ("assign_variable", {"variable": name, "value": value})


def use(text):
    return ("print_output", {"value": text})


maker = make_node("maker", node_id="a", blocks=[setv("raw", "'abc'"), setv("tmp", "1"), out("text", "raw.upper()")])
check("declared outputs are the ports", np_.node_interface(maker) == ([], ["text"]))
plain = make_node("plain", node_id="p", blocks=[setv("x", "1"), setv("y", "2")])
check("a node with no declarations still guesses from assigned variables", np_.node_interface(plain) == ([], ["x", "y"]))
taker = make_node("taker", node_id="b", blocks=[inp("text"), use("text")])
check("declared inputs are the input ports", np_.node_interface(taker) == (["text"], []))
check("names that are not identifiers are ignored", np_.declared_names(
    make_node("n", blocks=[out("1bad"), out("good"), out("good"), out("class")]), "node_output") == ["good"])
check("ports come with colours as before", [p["name"] for p in np_.node_ports(maker)] == ["text"])

wires = np_.data_wires([maker, taker])
check("a data wire runs from the node that sends out to the node that declares the input", wires == [("a", "b", ["text"])])
reader = make_node("reader", node_id="c", blocks=[use("tmp")])
check("a variable that was not sent out makes no wire when outputs are declared", np_.data_wires([maker, reader]) == [])
declare_only = make_node("t2", node_id="d", blocks=[inp("text")])
check("declaring an input is enough for the wire", np_.data_wires([maker, declare_only]) == [("a", "d", ["text"])])
check("a wire is not made to something that comes first", np_.data_wires([taker, maker]) == [])
own = make_node("o", node_id="e", blocks=[out("text", "'mine'"), use("text")])
check("reading a name this node sends out itself is not a wire", np_.data_wires([maker, own]) == [])
check("old behaviour: assigned variables still make wires without declarations",
      np_.data_wires([plain, make_node("q", node_id="q", blocks=[use("x")])]) == [("p", "q", ["x"])])

# function nodes: a returned expression that is not a name is called "result"
fn = make_node("greet", node_id="g", blocks=[("func_def", {"name": "greet", "params": "who", "_children": [
    ("return_statement", {"value": "'hi ' + who"})]})])
check("a returned expression is named result, not its code", np_.node_interface(fn) == (["who"], ["result"]))
fn2 = make_node("pair", node_id="h", blocks=[("func_def", {"name": "pair", "params": "", "_children": [
    ("return_statement", {"value": "a, b + 1"})]})])
check("several returns: names stay, expressions become result", np_.node_interface(fn2) == ([], ["a", "result"]))
fn3 = make_node("two", node_id="i", blocks=[("func_def", {"name": "two", "params": "", "_children": [
    ("return_statement", {"value": "x + 1, y + 1"})]})])
check("two unnamed results get distinct port names", np_.node_interface(fn3) == ([], ["result", "result_2"]))

# the blocks exist in every code language and write one line
root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "languages")
for lang in sorted(os.listdir(root)):
    if not os.path.isdir(os.path.join(root, lang, "blocks")) or lang == "html":
        continue
    blocks = with_generate_code(loader.load_language_pack(os.path.join(root, lang))[1])
    o, i = blocks.get("node_output"), blocks.get("node_input")
    check(f"{lang}: has Node Output and Node Input", o is not None and i is not None)
    if o and i:
        code = o["generate_code"]({"name": "total", "value": "5"}, [], lang)
        check(f"{lang}: Node Output writes one assignment line", "total" in code and "5" in code and code.count("\n") == 1)
        check(f"{lang}: Node Input writes one comment line", i["generate_code"]({"name": "total"}, [], lang).count("\n") == 1)
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
