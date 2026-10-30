"""Branch labels for call wires (pure rules, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import branch_labels as bl

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def call(name): return ("func_call", {"name": name, "args": ""})
def chip(name): return {"_nested_block": "func_call", "_nested_params": {"name": name, "args": ""}}
def branch(kind, cond, *kids):
    p = {"_children": list(kids)}
    if cond is not None: p["condition"] = cond
    return (kind, p)

def main():
    f = bl.call_branches
    check("no branches, no labels", f([call("a"), call("b")]) == {})
    check("empty / missing input", f([]) == {} and f(None) == {})
    check("call in an if gets its condition", f([branch("if_statement", "ok", call("a"))]) == {"a": "if ok"})
    check("if / elif / else each label their calls", f([
        branch("if_statement", "x > 1", call("a")),
        branch("elif_statement", "x > 0", call("b")),
        branch("else_statement", None, call("c"))]) == {"a": "if x > 1", "b": "elif x > 0", "c": "else"})
    check("a call outside every branch gets no label", f([call("a"), branch("if_statement", "ok", call("a"))]) == {})
    check("same name in two branches joins them", f([
        branch("if_statement", "ok", call("a")), branch("else_statement", None, call("a"))]) == {"a": "if ok / else"})
    check("nested branches join with >", f([
        branch("if_statement", "a", branch("else_statement", None, call("z")))]) == {"z": "if a > else"})
    check("the condition's own call is not inside the branch", f([
        branch("if_statement", chip("check"), call("a"))]) == {"a": "if check(...)"})
    check("a call chip in a branch body counts", f([
        branch("if_statement", "ok", ("assign_variable", {"variable": "x", "value": chip("g")}))]) == {"g": "if ok"})
    check("loops are not branches", f([("loop_for", {"_children": [call("a")]})]) == {})
    check("a call in a loop inside an if still has the if", f([
        branch("if_statement", "ok", ("loop_for", {"_children": [call("a")]}))]) == {"a": "if ok"})
    check("long conditions are cut", len(f([branch("if_statement", "x" * 80, call("a"))])["a"]) <= 3 + bl.MAX_COND)
    check("bad entries are skipped", f(["junk", ("func_call", None), branch("if_statement", "ok", call("a"))]) == {"a": "if ok"})
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
