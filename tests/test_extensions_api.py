"""What extensions see of the project (pure, no Tk)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import extensions_api as A

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

files = [{"title": "main.py", "language": "python", "imports": ["time", 5], "active_node_id": "n1",
          "nodes": [{"id": "n1", "name": "main", "kind": "function", "references": ["x"], "ref_kinds": {"x": "call"},
                     "blocks": [("print", {"value": "'hi'"}), ["if", {"cond": "x", "_children": [("print", {"value": "1"})], "_collapsed": True}]]},
                    {"id": "c1", "name": "Tools", "kind": "category", "child_nodes": [{"id": "n2", "name": "f", "kind": "function", "blocks": [], "ui": {"root": {}}}]}]}]
snap = A.snapshot(files, 0)
check("a snapshot is plain JSON", json.loads(json.dumps(snap)) == snap)
f = snap["files"][0]
check("file basics and imports (junk dropped)", f["title"] == "main.py" and f["language"] == "python" and f["imports"] == ["time"] and f["active_node"] == "n1")
n = f["nodes"][0]
check("blocks become {block, params} with nested children", n["blocks"][0] == {"block": "print", "params": {"value": "'hi'"}}
      and n["blocks"][1]["children"] == [{"block": "print", "params": {"value": "1"}}])
check("internal keys and derived data are left out", "_collapsed" not in n["blocks"][1]["params"] and "references" not in n and "ref_kinds" not in n)
check("categories hold their nodes; a UI node is flagged", f["nodes"][1]["children"][0]["name"] == "f" and f["nodes"][1]["children"][0]["has_ui"] is True and "blocks" not in f["nodes"][1])
files[0]["nodes"][0]["blocks"][0][1]["value"] = "changed"
check("it is a copy: changing the project later doesn't change it", snap["files"][0]["nodes"][0]["blocks"][0]["params"]["value"] == "'hi'")
check("the fingerprint changes with the project", A.fingerprint(A.snapshot(files)) != A.fingerprint(snap))
check("damaged data doesn't raise", A.snapshot([{"nodes": [None, 5, {"blocks": ["x", [1]]}]}])["files"][0]["nodes"][0]["blocks"] == [])
known = {"python": {"print": {"value": '"Hello"'}, "if_statement": {"condition": "True"}, "raw_code": {"code": ""}}}
base = [{"title": "m", "language": "python", "nodes": [{"id": "n1", "name": "main", "kind": "function", "blocks": [("print", {"value": "1"})]},
                                                      {"id": "c1", "name": "Cat", "kind": "category", "child_nodes": []}]}]
ids = iter(["a1", "a2", "a3"])
nf, summary = A.apply_edits(base, [
    {"op": "add_node", "name": "helper", "blocks": [{"block": "print", "params": {"value": "'x'"}}]},
    {"op": "add_node", "name": "Group", "kind": "category"},
    {"op": "add_node", "name": "inner", "parent": "c1"},
    {"op": "add_block", "node": "n1", "block": "if_statement", "params": {"condition": "x"}, "children": [{"block": "print"}], "index": 0},
    {"op": "rename_node", "node": "n1", "name": "start"}], known, id_factory=lambda: next(ids))
check("edits are applied to a copy", base[0]["nodes"][0]["name"] == "main" and len(base[0]["nodes"]) == 2)
names = [n["name"] for n in nf[0]["nodes"]]
check("nodes are added and renamed", names == ["start", "Cat", "helper", "Group"] and nf[0]["nodes"][1]["child_nodes"][0]["name"] == "inner")
blocks = nf[0]["nodes"][0]["blocks"]
check("blocks are inserted with defaults filled and children kept", blocks[0][0] == "if_statement" and blocks[0][1]["condition"] == "x"
      and blocks[0][1]["_children"] == [("print", {"value": '"Hello"'})] and blocks[1] == ("print", {"value": "1"}))
check("new function nodes get an order", isinstance(nf[0]["nodes"][2]["order"], int))
check("the summary says what happened", len(summary) == 5 and summary[0].startswith("Added function node 'helper'") and "Renamed 'main' to 'start'" in summary)
def refused(edits, **kw):
    try:
        A.apply_edits(base, edits, known, **kw); return None
    except A.EditError as e:
        return str(e)
check("an unknown block is refused", "no block 'nope'" in (refused([{"op": "add_block", "node": "n1", "block": "nope"}]) or ""))
check("an unknown parameter is refused", "unknown parameter" in (refused([{"op": "add_block", "node": "n1", "block": "print", "params": {"x": "1"}}]) or ""))
check("one bad operation changes nothing at all", refused([{"op": "rename_node", "node": "n1", "name": "ok"}, {"op": "bogus"}]) is not None and base[0]["nodes"][0]["name"] == "main")
check("bad file, node, parent and index are refused", all(refused(e) for e in (
    [{"op": "rename_node", "file": 5, "node": "n1", "name": "x"}], [{"op": "rename_node", "node": "zz", "name": "x"}],
    [{"op": "add_node", "name": "x", "parent": "n1"}], [{"op": "add_block", "node": "n1", "block": "print", "index": 99}],
    [{"op": "add_node", "name": ""}], [])))
check("blocks can't go into a category", refused([{"op": "add_block", "node": "c1", "block": "print"}]) is not None)
check("limits are enforced", refused([{"op": "add_node", "name": "x"}] * (A.MAX_OPS + 1)) is not None)
nf2, s2 = A.apply_edits(base, [{"op": "set_code", "node": "n1", "code": "a = 1\nb = 2"}], known,
                        code_to_blocks=lambda lang, text: [("raw_code", {"code": ln}) for ln in text.split("\n")])
check("set_code uses the code-to-blocks conversion", len(nf2[0]["nodes"][0]["blocks"]) == 2 and "Replaced the code" in s2[0])
check("set_code without a converter is refused", refused([{"op": "set_code", "node": "n1", "code": "x"}]) is not None)
print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
sys.exit(1 if FAILURES else 0)
