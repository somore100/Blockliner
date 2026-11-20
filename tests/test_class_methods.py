"""A Python class imports as a class node: a header node plus one node per method; the code regenerates exactly. Scripted UI test (run under Xvfb)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

SRC = '''import os

class Dog(Animal):
    """A dog."""
    legs = 4

    def __init__(self, name):
        super().__init__()
        self.name = name

    # speak up
    @property
    def loud(self):
        return self.name.upper()

    async def fetch(self, thing):
        """Go get it."""
        for x in range(3):
            print(x)

        return thing


def helper():
    return Dog("a")
'''

def same(a, b):
    """b is in a, apart from blank lines (importing drops those between statements, as for any import)."""
    keep = lambda t: [ln for ln in t.splitlines() if ln.strip()]
    ka, kb = keep(a), keep(b)
    return any(ka[i:i + len(kb)] == kb for i in range(len(ka) - len(kb) + 1))

CLASS_SRC = SRC[SRC.index("class Dog"):SRC.index("\n\ndef helper")]

def main():
    sp = portable.split_class_methods(SRC[SRC.index("class Dog"):SRC.index("def helper")])
    check("the class splits into header and three methods", sp and sp[0] == "Dog" and [m[0] for m in sp[2]] == ["__init__", "loud", "fetch"])
    check("a comment and decorator stay with their method", sp and sp[2][1][1].startswith("# speak up\n@property\ndef loud"))
    check("a method is dedented and keeps its width", sp and sp[2][0][1].startswith("def __init__") and sp[2][0][2] == 4)
    check("a class with no methods is not split", portable.split_class_methods("class A:\n    x = 1\n") is None)
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    try:
        chunks = portable.split_top_level(SRC)
        marked = portable.wrap_with_classes(chunks, "#", "python")
        check("the marked text still strips to the source", portable.strip_portable(marked) == SRC)
        app.load_portable_text(marked)
        tab = app.tabs[app.active_tab_index]
        top = tab["nodes"]
        kinds = [(n["name"], n["kind"]) for n in top]
        check(f"top level: imports, Dog class, helper ({kinds})", kinds == [("imports", "function"), ("Dog", "class"), ("helper", "function")])
        dog = top[1]
        check("the class holds a header and the methods", [c["name"] for c in dog["child_nodes"]] == ["Dog_header", "__init__", "loud", "fetch"])
        init = dog["child_nodes"][1]
        check("a method has real blocks, not just raw lines", any(b[0] != "raw_code" for b in init["blocks"]))
        gen = app.generate_code_for_tab(tab, "python")
        check("the generated code is the original", same(gen, CLASS_SRC))
        fetch = dog["child_nodes"][3]
        check("the per-node code is dedented", app.generate_code_for_node(fetch, "python").startswith("async def fetch"))
        # saved and reloaded
        import project_file
        data = project_file.build_project_data("python", top, tab["active_node_id"])
        _l, nodes2, _a, _n = project_file.parse_project_data(data, ["python"])
        tab2 = {"language": "python", "nodes": nodes2}
        check("a saved project reloads with the indent", same(app.generate_code_for_tab(tab2, "python"), CLASS_SRC))
        # the code panel's portable text round-trips
        port = app.generate_portable_for_tab(tab, "python", embed_meta=True)
        nodes3, _a, _d = app.nodes_from_portable_text(port, "python")
        check("the portable text reloads the same nodes", [c["name"] for c in nodes3[1]["child_nodes"]] == ["Dog_header", "__init__", "loud", "fetch"])
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
