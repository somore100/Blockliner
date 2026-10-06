"""Whole-project JSON Save/Load: full node tree round trip, old formats,
damaged data, opens on the Files layer in a new tab. Run under Xvfb."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import project_file as PF
import ui_codegen
from ui import BlocklinerUI
from ui_common import PRESET_LANGUAGES
from nodes_model import make_node, function_nodes_in_tree_order, find_node_by_id

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def pure():
    blk = [("print", {"value": "hi", "_children": [("print", {"value": "x"})]})]
    kid = make_node("method", node_id="m1", blocks=blk, order=3)
    cls = make_node("Game", node_id="c1", kind="class", child_nodes=[kid], locked=True)
    cat = make_node("Tools", node_id="cat1", kind="category", category="blue")
    a = make_node("a", node_id="a", blocks=[("x", {"p": 1})], order=None)
    a["canvas_x"], a["canvas_y"] = 10, 20
    a["order"] = None
    a["references"] = ["m1"]
    nodes = [cat, cls, a]
    text = PF.dumps("python", nodes, "m1")
    lang, got, active, notes = PF.parse_project_data(json.loads(text), PRESET_LANGUAGES)
    check("round trip keeps language/active/no notes", lang == "python" and active == "m1" and notes == [])
    check("kinds + class child + locked survive",
          [n["kind"] for n in got] == ["category", "class", "function"] and got[1]["child_nodes"][0]["id"] == "m1" and got[1]["locked"])
    check("blocks come back as tuples incl. nested children",
          got[1]["child_nodes"][0]["blocks"] == blk and isinstance(got[1]["child_nodes"][0]["blocks"][0], tuple)
          and isinstance(got[1]["child_nodes"][0]["blocks"][0][1]["_children"][0], tuple))
    check("order number and explicit None survive", got[1]["child_nodes"][0]["order"] == 3 and got[2]["order"] is None)
    check("position + category survive", got[2]["canvas_x"] == 10 and got[0]["category"] == "blue")
    check("references are not saved (derived)", "references" not in json.loads(text)["nodes"][2] and got[2]["references"] == [])
    # old formats
    for label, old in (("bare list", [["x", {"p": 1}]]), ("language+blocks", {"language": "rust", "blocks": [["x", {"p": 1}]]})):
        lang, n, act, notes = PF.parse_project_data(old, PRESET_LANGUAGES)
        check(f"old format {label}: one main node", len(n) == 1 and n[0]["id"] == "main" and n[0]["blocks"] == [("x", {"p": 1})] and act == "main" and notes)
    check("old format keeps its language", PF.parse_project_data({"language": "rust", "blocks": []}, PRESET_LANGUAGES)[0] == "rust")
    # damaged
    for label, bad in (("string", "hi"), ("empty dict", {}), ("nodes all junk", {"nodes": [1, "x"]}), ("number", 5)):
        try: PF.parse_project_data(bad, PRESET_LANGUAGES); ok = False
        except ValueError: ok = True
        check(f"rejected cleanly: {label}", ok)
    lang, n, act, notes = PF.parse_project_data({"language": "klingon", "active_node_id": "nope", "nodes": [
        {"id": "a", "name": "a", "blocks": [["x", {}], "junk", [1, 2]]},
        {"id": "a", "name": "dup"},
        {"id": "z", "name": "bad kind", "kind": "weird"},
        {"id": "k", "name": "cls", "kind": "class", "child_nodes": [None, {"id": "kk", "name": "kid"}]}]}, PRESET_LANGUAGES, "python")
    ids = [x["id"] for x in n]
    check("unknown language -> fallback + note", lang == "python" and any("klingon" in x for x in notes))
    check("bad blocks dropped, good kept", n[0]["blocks"] == [("x", {})])
    check("duplicate ids made unique", len(set(ids)) == len(ids) == 3)
    check("bad kind skipped, bad child skipped, good child kept", n[2]["child_nodes"][0]["id"] == "kk" and len(n[2]["child_nodes"]) == 1)
    check("unknown active id -> a real function node", find_node_by_id(n, act) is not None and find_node_by_id(n, act)["kind"] == "function")
    check("order filled in for legacy nodes", all("order" in x for x in function_nodes_in_tree_order(n)))

def main():
    pure()
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    ui_codegen.messagebox.showinfo = lambda *a, **k: None
    errs = []
    ui_codegen.messagebox.showerror = lambda *a, **k: errs.append(a)
    app.maybe_notify = lambda *a, **k: None
    tab = app.tabs[app.active_tab_index]
    fn = function_nodes_in_tree_order(tab["nodes"])
    bid = app.get_raw_code_block_id("python"); pn = app.get_raw_code_param_name(bid)
    fn[0]["blocks"] = [(bid, {pn: "one = 1"})]; app.project_blocks = fn[0]["blocks"]
    second = make_node("second", node_id="s2", blocks=[(bid, {pn: "two = 2"})], order=2)
    tab["nodes"].append(second); tab["active_node_id"] = "s2"
    app.project_blocks = second["blocks"]
    tmp = tempfile.mkdtemp(); path = os.path.join(tmp, "p.json")
    check("save writes", app._write_project_file(path))
    data = json.load(open(path))
    check("file is version 2 with every node", data["version"] == 2 and {n["id"] for n in data["nodes"]} >= {"s2", fn[0]["id"]})

    ui_codegen.filedialog.askopenfilename = lambda **k: path
    n_tabs = len(app.tabs)
    app.load_project()
    t = app.tabs[app.active_tab_index]
    check("dirty tab -> opens in a NEW tab", len(app.tabs) == n_tabs + 1 and not errs)
    check("loaded tab has all nodes + active node", find_node_by_id(t["nodes"], "s2") is not None and t["active_node_id"] == "s2" and len(t["nodes"]) == len(tab["nodes"]))
    check("active node's blocks are the live ones", app.project_blocks is find_node_by_id(t["nodes"], "s2")["blocks"])
    check("opens on the Files layer", app.view_mode == "files")
    check("title/path/clean", t["title"] == "p" and t["filepath"] == path and not t["dirty"])

    # old format file loads
    old = os.path.join(tmp, "old.json"); json.dump({"language": "python", "blocks": [[bid, {pn: "z = 9"}]]}, open(old, "w"))
    ui_codegen.filedialog.askopenfilename = lambda **k: old
    app.load_project()
    t = app.tabs[app.active_tab_index]
    check("old-format file loads as one main node", not errs and len(t["nodes"]) == 1 and t["nodes"][0]["blocks"][0][1][pn] == "z = 9")
    # garbage file -> error popup, no new tab
    bad = os.path.join(tmp, "bad.json"); open(bad, "w").write("[1, 2")
    ui_codegen.filedialog.askopenfilename = lambda **k: bad
    n = len(app.tabs); app.load_project()
    check("garbage file: error shown, no tab added", len(errs) == 1 and len(app.tabs) == n)
    # blank tab is reused; a blank-looking tab with several nodes is not
    ui_codegen.filedialog.askopenfilename = lambda **k: path
    app.new_tab(); n = len(app.tabs); app.load_project()
    check("blank untouched tab is reused", len(app.tabs) == n and app.tabs[app.active_tab_index]["filepath"] == path)
    app.new_tab(); app.tabs[app.active_tab_index]["nodes"].append(make_node("empty2", node_id="e2"))
    n = len(app.tabs); app.load_project()
    check("tab with several (empty) nodes is NOT overwritten", len(app.tabs) == n + 1)
    app.destroy()
    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
