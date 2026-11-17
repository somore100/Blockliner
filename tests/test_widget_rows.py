"""ui_node.widget_rows / triggers_for: a window's widgets as rows for the Nodes layer (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_pack
from nodes_model import make_node
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
fails = []
def check(name, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)

pack = ui_pack.find_packs([ROOT], "python")[0][0]
tree = UITree.new(pack.id, root_type="window", root_name="root", props=pack.defaults("window"), is_container=pack.is_container)
frame = tree.add(tree.root["id"], "frame", props=pack.defaults("frame"))
btn = tree.add(frame, "button", props=pack.defaults("button"))
lab = tree.add(tree.root["id"], "label", props=pack.defaults("label"))
tree.set_screen(frame)
node = ui_node.make_ui_node("Main", "ui1", tree)
save = make_node("on_save", node_id="f1", kind="function", blocks=[])
look = {"f1": save}.get

rows = ui_node.widget_rows(node, pack, look)
check("every widget is a row, the window is not", [r["id"] for r in rows] == [frame, btn, lab])
check("depth follows the nesting", [r["depth"] for r in rows] == [0, 1, 0])
check("a screen is marked", [r["screen"] for r in rows] == [True, False, False])
check("the pack's wording for the type", rows[1]["label"] == "Button")
check("a frame or label has no events", rows[0]["events"] == [] and rows[2]["events"] == [])
ev = rows[1]["events"]
check("a button offers its event, unlinked", len(ev) == 1 and ev[0]["key"] == "command" and ev[0]["handler_id"] is None and ev[0]["handler"] is None)

tree.set_event(btn, "command", "f1")
ui_node.store_tree(node, tree)
ev = ui_node.widget_rows(node, pack, look)[1]["events"][0]
check("linked: the function node is there", ev["handler_id"] == "f1" and ev["handler"] is save and not ev["is_window"])
tree.set_event(btn, "command", "gone")
ui_node.store_tree(node, tree)
ev = ui_node.widget_rows(node, pack, look)[1]["events"][0]
check("a broken link keeps its id but has no node", ev["handler_id"] == "gone" and ev["handler"] is None)
check("a node without a UI has no rows", ui_node.widget_rows({"name": "x"}, pack, look) == [] and ui_node.widget_rows(None, pack, look) == [])

tree.set_event(btn, "command", "f1")
ui_node.store_tree(node, tree)
found = ui_node.triggers_for([node], "f1", lambda _n: pack, look)
check("triggers: which widget event runs a function", found == [("Main", tree.find(btn)["name"], "On click")])
check("triggers: none for another function", ui_node.triggers_for([node], "zzz", lambda _n: pack, look) == [])
check("handler names: plain event", ui_node.handler_base_name("btn_save", "command") == "on_btn_save_command")
check("handler names: <<Virtual>> events are tidied", ui_node.handler_base_name("combo", "<<ComboboxSelected>>") == "on_combo_combobox_selected")
print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
