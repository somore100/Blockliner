"""portable.split_top_level: top-level code separated by blank lines becomes separate nodes (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

T = 'import os\nimport sys\n\nA = 1\nB = 2\n\n# note\nprint(A)\nprint(B)\n\ndef f():\n    x = 1\n\n    return x\n\nz = [\n 1,\n\n 2]\n\nw = """a\n\nb"""\n'
chunks = portable.split_top_level(T)
names = [n for n, _c in chunks]
check("nothing is lost", "".join(c for _n, c in chunks) == T)
check("each blank-line group is a node", names == ["imports", "top_level", "top_level", "f", "z", "top_level"])
check("a comment stays with its group", chunks[2][1].startswith("# note"))
check("a blank line inside a function does not split it", chunks[3][1].count("return x") == 1 and chunks[3][1].startswith("def f"))
check("a blank line inside a bracket or a string does not split", "2]" in chunks[4][1] and chunks[5][1].count('"""') == 2)
check("one group stays one node", portable.split_top_level("a = 1\nb = 2\n") == [("top_level", "a = 1\nb = 2\n")])
check("the ids are unique", len(set(portable.unique_ids(names))) == len(names))
print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
