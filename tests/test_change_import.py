"""change_import: AI-suggested changes by node name and quoted code (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import change_import as ci

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

CHAT = '''Sure! Here are the changes.

=== edit: parse_args
```
<<<<<<< SEARCH
parser.add_argument("-v")
=======
parser.add_argument("-v", action="store_true")
>>>>>>> REPLACE
```

=== replace: main
```python
def main():
    print("hi")
```

=== new: helper
def helper():
    return 1

=== edit: Dog.fetch
<<<<<<< SEARCH
x = 1
=======
x = 2
>>>>>>> REPLACE
'''
ops, problems = ci.parse(CHAT)
check("four changes, no problems", [o.kind for o in ops] == ["edit", "replace", "new", "edit"] and not problems)
check("code fences are ignored", ops[1].code == 'def main():\n    print("hi")\n')
check("an edit holds its search and replacement", ops[0].edits == [('parser.add_argument("-v")', 'parser.add_argument("-v", action="store_true")')])
check("no ===: a clear message", ci.parse("just words")[1])
check("an unclosed block is reported", ci.parse("=== edit: a\n<<<<<<< SEARCH\nx\n=======\ny\n")[1])

check("exact edit", ci.apply_edit("a = 1\nb = 2\n", "b = 2", "b = 3") == "a = 1\nb = 3\n")
check("indentation and blank lines do not matter", ci.apply_edit("def f():\n    a = 1\n\n    b = 2\n", "a = 1\nb = 2", "a = 5") == "def f():\n    a = 5\n")
check("the replacement takes the code's indentation", ci.apply_edit("def f():\n        a = 1\n", "    a = 1", "    a = 2\n    b = 3") == "def f():\n        a = 2\n        b = 3\n")
for bad, why in (("zzz", "not found"), ("a = 1", "twice")):
    try:
        ci.apply_edit("a = 1\nb = 2\na = 1\n", bad, "q")
        check(f"{why} is refused", False)
    except ValueError:
        check(f"{why} is refused", True)

nodes = [{"id": "1", "name": "parse_args", "kind": "function"}, {"id": "2", "name": "main", "kind": "function"},
         {"id": "3", "name": "Dog", "kind": "class", "child_nodes": [{"id": "4", "name": "fetch", "kind": "function"}]},
         {"id": "5", "name": "fetch", "kind": "function"}]
code = {"1": 'parser.add_argument("-v")\n', "2": "def main():\n    pass\n", "4": "x = 1\n", "5": "y = 1\n"}
ch = ci.plan(nodes, ops, lambda n: code[n["id"]])
check("all four plan fine", [c.ok for c in ch] == [True] * 4)
check("the qualified name picks the method", ch[3].node["id"] == "4" and ch[3].new == "x = 2\n")
check("replace and new carry the code", ch[1].new.startswith("def main") and ch[2].node is None)
ops2, _ = ci.parse("=== edit: fetch\n<<<<<<< SEARCH\ny\n=======\nz\n>>>>>>> REPLACE\n=== edit: nope\n<<<<<<< SEARCH\ny\n=======\nz\n>>>>>>> REPLACE\n=== new: main\ncode = 1\n")
ch2 = ci.plan(nodes, ops2, lambda n: code[n["id"]])
check("two nodes called fetch: the plain name is ambiguous or unique", ch2[0].ok or "more than one" in ch2[0].error)
check("an unknown node is an error", not ch2[1].ok and "no node" in ch2[1].error)
check("a new node that exists is an error", not ch2[2].ok)
ops3, _ = ci.parse("=== edit: main\n<<<<<<< SEARCH\npass\n=======\nprint(1)\n>>>>>>> REPLACE\n=== edit: main\n<<<<<<< SEARCH\nprint(1)\n=======\nprint(2)\n>>>>>>> REPLACE\n")
ch3 = ci.plan(nodes, ops3, lambda n: code[n["id"]])
check("two edits to one node build on each other", ch3[1].ok and ch3[1].new == "def main():\n    print(2)\n")
print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
