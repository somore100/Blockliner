"""Importing Python code: a multi-line statement is one block, an unmatched header keeps its body inside it, raw lines
inside a body don't get extra indent, and the code regenerates the same. Scripted UI test (run under Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

SRC = '''def f(a):
    """Docs over
    two lines."""
    with open(a) as g, open(a) as h:
        data = g.read()
        total = compute(data,
                        h)
        yield total
    x = {
        "k": 1,
    }
    del x
    return 1
'''

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        blocks, matched, raw = app.import_code_to_blocks(SRC)
        regen = "".join(app.render_block_list(blocks, "python"))
        check("it regenerates exactly", regen.strip() == SRC.strip())
        fn = blocks[0]
        kinds = [b[0] for b in fn[1]["_children"]]
        check(f"the def holds docstring, with, dict, del, return ({kinds})", kinds == ["raw_code", "raw_block", "raw_code", "raw_code", "return_statement"])
        doc = fn[1]["_children"][0][1]
        check("the docstring is one block of two lines", len(doc) == 1 and list(doc.values())[0].count("\n") == 1)
        wb = fn[1]["_children"][1]
        check("the with block keeps its header and three statements inside", wb[1]["header"].startswith("with open") and len(wb[1]["_children"]) == 3)
        call = wb[1]["_children"][1]
        check("the multi-line call is one block", call[0] == "raw_code" and list(call[1].values())[0] == "total = compute(data,\n                h)")
        # a raw line in a body has no extra indent
        b2, _m, _r = app.import_code_to_blocks("def g():\n    x.y.z\n")
        check("a raw line in a body is not indented twice", "".join(app.render_block_list(b2, "python")) == "def g():\n    x.y.z\n")
        # statements that end in ':' with a trailing comment stay line by line (nothing is lost)
        b3, _m, _r = app.import_code_to_blocks("with a:  # note\n    pass\n")
        check("a header with a comment is kept", "# note" in "".join(app.render_block_list(b3, "python")))
        check("the custom block shows up as a block", app.get_raw_container_id() == "raw_block")
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
