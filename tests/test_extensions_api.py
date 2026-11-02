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
print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
sys.exit(1 if FAILURES else 0)
