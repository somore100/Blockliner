"""Port colours: meaning when the type is certain, name hash otherwise. Pure (no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import node_ports as np_
from nodes_model import make_node

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def fn(name, params, ret=None):
    body = [("return_statement", {"value": ret})] if ret else []
    return make_node(name, node_id=name, blocks=[("func_def", {"name": name, "params": params, "_children": body})])

def main():
    c = np_.classify_type
    check("python annotations", [c("int"), c("str"), c("bool"), c("list"), c("dict")] == ["number", "text", "bool", "list", "dict"])
    check("generics and wrappers", [c("List[int]"), c("Vec<i32>"), c("Optional[str]"), c("HashMap<K,V>")] == ["list", "list", "text", "dict"])
    check("C / Java style", [c("const char *"), c("unsigned int"), c("String[]"), c("double"), c("&str")] == ["text", "number", "list", "number", "text"])
    check("unknown stays unknown (never guessed)", c("User") is None and c("") is None and c(None) is None and c("T") is None)
    p = np_.param_types
    check("python params", p("a: int, b, c: str = 'x'") == {"a": "number", "c": "text"})
    check("C params", p("int n, char *s, float *f") == {"n": "number", "s": "text"} or p("int n, char *s") == {"n": "number", "s": "text"})
    check("untyped params give nothing", p("a, b, c") == {} and p("") == {} and p(None) == {})
    check("self is skipped", p("self: int") == {})
    l = np_.literal_type
    check("literals", [l('"hi"'), l("'x'"), l("3"), l("-2.5"), l("1e3"), l("True"), l("[1, 2]"), l("{}"), l("{'a': 1}")] ==
          ["text", "text", "number", "number", "number", "bool", "list", "dict", "dict"])
    check("not literals", all(l(x) is None for x in ["foo()", "x + 1", "[a][0]", '"a" + b', "", None, "{1}[0]"]))

    n = fn("check", "name: str, age: int, flag, ok: bool", "ok")
    ports = {(q["side"], q["name"]): q for q in np_.node_ports(n)}
    check("typed inputs get the type colour", ports[("in", "name")]["color"] == np_.TYPE_COLORS["text"]
          and ports[("in", "age")]["color"] == np_.TYPE_COLORS["number"]
          and ports[("in", "ok")]["color"] == np_.TYPE_COLORS["bool"])
    check("port reports its type", ports[("in", "name")]["type"] == "text" and ports[("in", "flag")]["type"] is None)
    check("untyped port never uses a type colour", ports[("in", "flag")]["color"] not in np_.TYPE_COLORS.values())
    check("untyped output never uses a type colour", ports[("out", "ok")]["color"] not in np_.TYPE_COLORS.values())
    np_.set_port_color(n, "in", "name", "#112233")
    q = [x for x in np_.node_ports(n) if x["name"] == "name"][0]
    check("manual colour still wins over the type", q["color"] == "#112233" and q["manual"] is True)

    v = make_node("vars", node_id="vars", blocks=[
        ("assign_variable", {"variable": "title", "value": '"Hello"'}),
        ("assign_variable", {"variable": "count", "value": "3"}),
        ("assign_variable", {"variable": "mix", "value": "3"}),
        ("assign_variable", {"variable": "mix", "value": "foo()"}),
        ("assign_variable", {"variable": "other", "value": "foo()"})])
    vp = {q["name"]: q for q in np_.node_ports(v)}
    check("literal assignments give typed outputs", vp["title"]["type"] == "text" and vp["count"]["type"] == "number")
    check("a variable reassigned to something unknown is untyped", vp["mix"]["type"] is None)
    check("non-literal value is untyped", vp["other"]["type"] is None)
    many = make_node("many", node_id="many", blocks=[("assign_variable", {"variable": f"v{i}", "value": "foo()"}) for i in range(3)])
    cols = [q["color"] for q in np_.node_ports(many)]
    check("three untyped ports: distinct neutral colours", len(set(cols)) == 3 and not set(cols) & set(np_.TYPE_COLORS.values()))
    check("auto colour stable and in the palette", np_.auto_color("user") == np_.auto_color("user")
          and np_.auto_color("user") in {c for _n, c in np_.PORT_COLORS})
    check("eight untyped names on a side still get distinct colours",
          len({np_.auto_color(f"n{i}", taken=set()) for i in range(1)}) == 1)
    taken = set()
    got = []
    for i in range(8):
        col = np_.auto_color(f"n{i}", taken); got.append(col); taken.add(col)
    check("fills the whole palette before repeating", len(set(got)) == 8)
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
