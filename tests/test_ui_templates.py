"""UI windows as node templates (pure, no Tk)."""
import os, sys, itertools, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import node_templates as N
import ui_node, ui_gen, ui_pack
import ui_designer_model as M
from ui_tree import UITree

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    pack, _n = ui_pack.load_pack(os.path.join(HERE, "ui_packs", "python", "tkinter"))
    entries, notes = N.load_folder(os.path.join(HERE, "nodes"), "python")
    ui_entries = [e for e in entries if N.ui_pack_id(e["template"])]
    check("prebuilt UI templates load cleanly", len(ui_entries) >= 5 and not notes)
    check("UI templates are not offered in other languages",
          not [e for e in N.load_folder(os.path.join(HERE, "nodes"), "javascript")[0] if N.ui_pack_id(e["template"])])
    ids = (f"n{i}" for i in itertools.count())
    good = True
    for e in ui_entries:
        node, nts = N.instantiate(e["template"], {"title": "Hello"}, set(), None, None, lambda: next(ids))
        tree = ui_node.load_tree(node, pack)
        res = ui_gen.generate(tree, pack) if tree else None
        good &= ui_node.is_ui_node(node) and tree is not None and tree.pack_id == pack.id and not nts \
            and not res["problems"] and tree.root["props"]["title"] == "Hello"
    check("every prebuilt UI template becomes a working designer node (title filled in)", good)

    # save a live UI node as a template: events dropped, ui kept
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    b = M.add_widget(t, pack, "button")
    t.set_event(b, "command", "some_function_id")
    node = ui_node.make_ui_node("Form", "u1", t)
    node["blocks"] = [("raw_code", {"code": "generated"})]
    tpl = N.build_template(node)
    check("saving keeps the window and drops event links and generated blocks",
          tpl["blocks"] == [] and tpl["ui"]["root"]["children"][0]["events"] == {})
    parsed, pn = N.parse_template(tpl)
    check("a saved UI template reads back", parsed is not None and N.ui_pack_id(parsed) == pack.id and not pn)
    with tempfile.TemporaryDirectory() as d:
        path = N.save_custom(d, "python", tpl)
        loaded, _ = N.load_folder(d, "python")
        check("save_custom + load_folder round trip", len(loaded) == 1 and loaded[0]["template"]["ui"] == parsed["ui"])
    ui_node.detach(node)
    check("a detached (code-only) UI node saves as plain blocks", "ui" not in N.build_template(node))
    bad = dict(tpl); bad["ui"] = {"format": "nope"}
    check("a damaged UI document is refused", N.parse_template(bad)[0] is None)
    print("\nFAILURES:", FAILURES)

main()
