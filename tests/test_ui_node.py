"""UI-builder nodes: pure parts (ui_node, save/load, portable round trip). No Tk."""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable as P
import project_file
import ui_node
import ui_pack
from nodes_model import make_node
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    pack, _n = ui_pack.load_pack(os.path.join(ROOT, "python", "tkinter"))
    tree = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    btn = tree.add(tree.root["id"], "button", props={"text": "Go"}, layout={"manager": "grid", "row": 0, "column": 0})
    tree.set_event(btn, "command", "h1")
    node = ui_node.make_ui_node("UI 1", "u1", tree, order=2)
    check("make_ui_node: a plain function node plus the document", node["kind"] == "function" and ui_node.is_ui_node(node)
          and node["order"] == 2 and node["blocks"] == [] and not ui_node.is_detached(node))
    check("is_ui_node on other things", not ui_node.is_ui_node(make_node("f")) and not ui_node.is_ui_node(None) and not ui_node.is_ui_node({"ui": 5}))
    check("widget_count leaves the window out", ui_node.widget_count(node) == 1 and ui_node.widget_count(make_node("f")) == 0)
    check("function_name is a valid identifier", ui_node.function_name(node) == "build_UI_1" and ui_node.function_name({"name": "!!"}) == "build_ui")

    resolve = {"h1": "on_go"}.get
    text, problems = ui_node.generate_text(node, pack, resolve)
    check("generate_text gives code and no problems", text and "command=on_go" in text and "def build_UI_1():" in text and problems == [])
    probs = ui_node.regenerate(node, pack, "raw_code", "code", resolve)
    check("regenerate writes one raw block", probs == [] and len(node["blocks"]) == 1 and node["blocks"][0][0] == "raw_code"
          and node["blocks"][0][1]["code"] == text.rstrip("\n"))
    before = node["blocks"]
    ui_node.regenerate(node, pack, "raw_code", "code", resolve)
    check("regenerating twice keeps the same blocks", node["blocks"] == before)
    held = node["blocks"]
    old_title = node[ui_node.UI_KEY]["root"]["props"].get("title")
    node[ui_node.UI_KEY]["root"]["props"]["title"] = "Changed"
    ui_node.regenerate(node, pack, "raw_code", "code", resolve)
    check("regenerate updates the list in place (project_blocks aliases it)",
          node["blocks"] is held and "Changed" in held[0][1]["code"])
    node[ui_node.UI_KEY]["root"]["props"]["title"] = old_title
    ui_node.regenerate(node, pack, "raw_code", "code", resolve)
    check("matches_code: exact, with edges ignored, edited", ui_node.matches_code(node, pack, text, resolve)
          and ui_node.matches_code(node, pack, "\n" + text + "\n\n", resolve) and not ui_node.matches_code(node, pack, text + "x = 1", resolve))

    ui_node.detach(node); node["blocks"] = [("raw_code", {"code": "hand edited"})]
    check("detached nodes are never regenerated", ui_node.regenerate(node, pack, "raw_code", "code", resolve) is None
          and node["blocks"][0][1]["code"] == "hand edited")
    ui_node.reattach(node)
    ui_node.regenerate(node, pack, "raw_code", "code", resolve)
    check("reattach + regenerate replaces hand edits", node["blocks"][0][1]["code"] == text.rstrip("\n"))
    check("no raw block id / no pack: nothing happens", ui_node.regenerate(node, pack, None, "code") is None and ui_node.regenerate(node, None, "raw_code", "code") is None)

    wrong = copy.deepcopy(node); wrong["ui"]["pack"] = "python/other"
    check("a tree from another pack isn't generated", ui_node.generate_text(wrong, pack)[0] is None)
    broken = copy.deepcopy(node); broken["ui"] = {"format": "x"}
    check("damaged documents give no text, not an exception", ui_node.load_tree(broken) is None and ui_node.generate_text(broken, pack)[0] is None)
    newer = copy.deepcopy(node); newer["ui"]["version"] = 99
    check("newer-version documents are not generated", ui_node.generate_text(newer, pack)[0] is None)

    # ---- project file round trip
    main_node = make_node("main", node_id="main", blocks=[], order=1)
    nodes = [main_node, node]
    data = project_file.build_project_data("python", nodes, "main")
    back_lang, back_nodes, active, notes = project_file.parse_project_data(json.loads(json.dumps(data)), ["python"])
    b = [n for n in back_nodes if n["id"] == "u1"][0]
    check("project save/load keeps the UI document and blocks", ui_node.is_ui_node(b) and b["ui"] == node["ui"] and b["blocks"] == node["blocks"] and notes == [])
    ui_node.detach(node)
    data = project_file.build_project_data("python", nodes, "main")
    b = [n for n in project_file.parse_project_data(json.loads(json.dumps(data)), ["python"])[1] if n["id"] == "u1"][0]
    check("the detached flag round-trips", ui_node.is_detached(b))
    data["nodes"][1]["ui"] = {"format": "garbage"}
    b = [n for n in project_file.parse_project_data(json.loads(json.dumps(data)), ["python"])[1] if n["id"] == "u1"][0]
    check("a damaged UI document loads as a plain function node", not ui_node.is_ui_node(b) and b["kind"] == "function")
    plain = make_node("f", node_id="f")
    check("plain nodes get no UI keys", "ui" not in project_file.build_project_data("python", [plain], "f")["nodes"][0])

    # ---- portable round trip
    ui_node.reattach(node)
    meta = P.build_metadata(nodes, "python", "main")
    check("portable metadata carries the document", meta["nodes"]["u1"]["ui"] == node["ui"] and "ui_detached" not in meta["nodes"]["u1"]
          and "ui" not in meta["nodes"]["main"])
    chunks = []
    for n, body in ((main_node, "x = 1\n"), (node, text)):
        s, e = P.node_marker_lines(n["id"], "#")
        chunks.append((s, body, e, ""))
    ptext = P.assemble("", chunks, "", P.render_meta_block(meta, "#"))
    top, _active, diag = P.rebuild_nodes(ptext, "python")
    u = [n for n in top if n["id"] == "u1"][0]
    check("portable import restores the document and the code", u["ui"] == node["ui"] and u["code"].strip() == text.strip() and diag == [])
    check("the restored code still matches the tree (stays attached)", ui_node.matches_code(u, pack, u["code"], resolve))
    check("an edited export no longer matches (would be detached)", not ui_node.matches_code(u, pack, u["code"] + "\nprint('hi')", resolve))
    meta["nodes"]["u1"]["ui"] = {"format": "garbage"}
    ptext2 = P.assemble("", chunks, "", P.render_meta_block(meta, "#"))
    u2 = [n for n in P.rebuild_nodes(ptext2, "python")[0] if n["id"] == "u1"][0]
    check("portable import drops a damaged document", "ui" not in u2)

    src, probs = ui_node.preview_source(node, pack, resolve)
    check("preview: stubs the handler before the build function and ends with the run lines",
          src is not None and probs == [] and "def on_go(*args, **kwargs):" in src
          and src.index("def on_go") < src.index("def build_UI_1") and "import tkinter" in src.split("def on_go")[0]
          and src.rstrip().endswith("ui.root.mainloop()"))
    check("preview source compiles", compile(src, "<preview>", "exec") is not None)
    class Other: id = "web/html"
    check("preview: refuses non-Python packs", ui_node.preview_source(node, Other())[0] is None)

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
