"""statements.statement_end: where a Python statement ends (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from statements import statement_end as end

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

L = ['x = 1', '"""doc', 'more"""', 'y = [1,', '  2]', 'z = "a" \\', '  "b"', 'if (a and', '    b):', '    pass',
     'w = f(  # (', '  1)', 's = "(("', 't = 1  # [', 'u = 2']
check("one line", end(L, 0) == 0)
check("a docstring over lines", end(L, 1) == 2)
check("an open bracket", end(L, 3) == 4)
check("a trailing backslash", end(L, 5) == 6)
check("a compound header over lines is not grouped", end(L, 7) == 7)
check("a comment's bracket is ignored", end(L, 10) == 11)
check("a bracket inside a string is ignored", end(L, 12) == 12)
check("a bracket in a trailing comment is ignored", end(L, 13) == 13 and end(L, 14) == 14)
check("an unclosed bracket stops at the end of the text", end(['a = f(', 'b'], 0) == 1)
print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
