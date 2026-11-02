"""Document type detection and the 'type' key on saves."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import doc_types, project_file
from nodes_model import make_node

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

CB = doc_types.CODEBUILDER
check("type key wins", doc_types.detect({"type": "multiscript.workflow", "nodes": []}) == "multiscript.workflow")
check("v3 shape", doc_types.detect({"format": "blockliner-project", "version": 3, "files": []}) == CB)
check("v2 shape", doc_types.detect({"version": 2, "nodes": [{}]}) == CB)
check("v1 blocks", doc_types.detect({"blocks": []}) == CB)
check("bare list", doc_types.detect([]) == CB)
check("unknown dict", doc_types.detect({"hello": 1}) is None)
check("not json obj", doc_types.detect("x") is None)
check("known ok", doc_types.unsupported_message({"files": []}) is None)
check("unknown type message", "isn't installed" in doc_types.unsupported_message({"type": "x.y"}))
check("not project message", "not a Blockliner project" in doc_types.unsupported_message({"a": 1}))

node = make_node("main", node_id="main", blocks=[])
single = project_file.build_project_data("python", [node], "main")
check("single typed", single["type"] == CB and single["format"] == "blockliner-project" and single["version"] == 2)
ws = project_file.build_workspace_data([{"title": "A", "language": "python", "nodes": [node], "active_node_id": "main"}], 0)
check("workspace typed", ws["type"] == CB and ws["version"] == 3)
check("files not typed", all("type" not in f for f in ws["files"]))
files, ai, _ = project_file.parse_workspace_data(ws, ["python"], "python")
check("round trip", len(files) == 1 and ai == 0)

print("ALL OK" if not fails else f"FAILURES: {fails}")
