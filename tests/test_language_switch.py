"""Switching a file's language: what is lost, and when to refuse (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import language_switch as L
import ui_node
LANGUAGE_EXTENSIONS = {".py": "python", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c"}   # same order as ui_common

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

def node(name, blocks=(), **extra):
    return dict({"id": name, "name": name, "blocks": list(blocks)}, **extra)

empty = {"language": "python", "nodes": [node("main")]}
check("an empty file switches freely", L.verdict(L.assess(empty, "c")) == "nothing")
check("the same language is nothing", L.verdict(L.assess(empty, "python")) == "nothing")

full = {"language": "python", "nodes": [node("main", [("print_output", {})]),
                                        node("cat", child_nodes=[node("inner", [("x", {})])])]}
info = L.assess(full, "csharp")
check("blocks in nested nodes are found", info["with_blocks"] == ["main", "inner"])
check("a file with blocks asks", L.verdict(info) == "ask")

ui = {"language": "python", "nodes": [node("main", [("x", {})]), node("UI 2", ui={"pack": "tkinter"})]}
check("a UI node is recognised", ui_node.is_ui_node(ui["nodes"][1]) and L.assess(ui, "c")["ui_nodes"] == ["UI 2"])
check("a file with a UI design refuses", L.verdict(L.assess(ui, "c")) == "refuse")
check("...but not when the language stays", L.verdict(L.assess(ui, "python")) == "nothing")

working = full["nodes"][0]["blocks"]
L.clear_blocks(full)
check("clearing empties every node, in place", working == [] and full["nodes"][1]["child_nodes"][0]["blocks"] == [])

check("file endings", L.extension_for("python", LANGUAGE_EXTENSIONS) == ".py" and L.extension_for("cpp", LANGUAGE_EXTENSIONS) == ".cpp"
      and L.extension_for("c", LANGUAGE_EXTENSIONS) == ".c" and L.extension_for("klingon", LANGUAGE_EXTENSIONS) == "")

print("ALL OK" if not fails else f"FAILURES: {fails}")
