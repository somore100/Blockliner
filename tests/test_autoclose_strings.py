"""Quote handling in auto-close (pure helpers, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import code_autoclose as A

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

check("f before a quote is a string prefix", A.string_prefix_before("print(f") and A.string_prefix_before("x = rb") and A.string_prefix_before("f"))
check("the end of a word is not a prefix", not A.string_prefix_before("print(if") and not A.string_prefix_before("of") and not A.string_prefix_before("buf"))
check("inside a string after an odd number of quotes", A.inside_string('print(f"your age is {age}', '"') and A.inside_string("x = 'a", "'"))
check("not inside after a closed string", not A.inside_string('print("a")', '"') and not A.inside_string("", '"'))
check("an escaped quote does not count", A.inside_string('"a\\"b', '"') and not A.inside_string('"a\\"b"', '"'))
print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
sys.exit(1 if FAILURES else 0)
