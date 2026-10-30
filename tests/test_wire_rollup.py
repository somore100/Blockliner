"""Rolled-up wires (pure rules, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wire_rollup as wr
import wire_kinds as wk

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def n(i, refs=(), kinds=None, uses=(), kids=None):
    d = {"id": i, "references": list(refs), "ref_kinds": kinds or {}, "data_uses": list(uses)}
    if kids is not None: d["kind"] = "category"; d["child_nodes"] = kids
    return d

def main():
    cat = n("cat", kids=[n("x"), n("y")])
    e = wr.rolled_edges([n("a", refs=["x"]), cat])
    check("call into a category rolls up to the box", e == [{"src": "a", "dst": "cat", "kind": "call", "count": 1, "vars": []}])
    e = wr.rolled_edges([n("a"), n("cat", kids=[n("x", refs=["a"])])])
    check("call out of a category", [(x["src"], x["dst"]) for x in e] == [("cat", "a")])
    check("calls inside one category are not drawn", wr.rolled_edges([n("cat", kids=[n("x"), n("y", refs=["x"])])]) == [])
    check("plain visible-to-visible edges are left to the normal wires",
          wr.rolled_edges([n("a", refs=["b"]), n("b")]) == [])
    e = wr.rolled_edges([n("a", refs=["x", "y"]), n("cat", kids=[n("x"), n("y")])])
    check("two calls into one box merge, count 2", len(e) == 1 and e[0]["count"] == 2)
    e = wr.rolled_edges([n("a", refs=["x"], kinds={"x": "data"}), n("c", kids=[n("x")])])
    check("kind is kept (result used = data)", e[0]["kind"] == "data")
    e = wr.rolled_edges([n("a", refs=["x", "y"], kinds={"y": "data"}), n("c", kids=[n("x"), n("y")])])
    check("different kinds stay separate", sorted(x["kind"] for x in e) == ["call", "data"])
    e = wr.rolled_edges([n("c", kids=[n("p")]), n("u", uses=[{"id": "p", "vars": ["v", "w"]}])])
    check("data wire producer -> user rolled", e == [{"src": "c", "dst": "u", "kind": "data", "count": 1, "vars": ["v", "w"]}])
    e = wr.rolled_edges([n("c", kids=[n("p")]), n("d", kids=[n("u", uses=[{"id": "p", "vars": ["v"]}])])])
    check("data wire between two categories", [(x["src"], x["dst"]) for x in e] == [("c", "d")])
    check("edge to a node outside the shown list is skipped", wr.rolled_edges([n("a", refs=["zzz"])]) == [])
    e = wr.rolled_edges([n("a", refs=["x"]), n("c", kids=[n("sub", kids=[n("x")])])])
    check("nested categories roll up to the outermost shown box", [(x["src"], x["dst"]) for x in e] == [("a", "c")])
    check("self reference inside a box ignored", wr.rolled_edges([n("c", kids=[n("x", refs=["x"])])]) == [])
    check("empty / missing fields are fine", wr.rolled_edges([{"id": "q"}]) == [] and wr.rolled_edges([]) == [])
    ent = wk.legend_entries({"data", "call", "bogus"})
    check("legend: only known kinds present, in KINDS order", [e[0] for e in ent] == ["call", "data"])
    check("legend: each entry has a label and the kind's style", all(e[1] and e[2] == wk.STYLES[e[0]] for e in ent))
    check("legend: nothing drawn, no entries", wk.legend_entries([]) == [] and wk.legend_entries(None) == [])
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
