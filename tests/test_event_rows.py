"""ui_node.event_rows: what each widget of a UI window does, for the Behaviour
view. Pure, no Tk."""
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
b1 = tree.add(frame, "button", props=pack.defaults("button"))
b2 = tree.add(tree.root["id"], "button", props=pack.defaults("button"))
lab = tree.add(frame, "label", props=pack.defaults("label"))
node = ui_node.make_ui_node("Main", "ui1", tree)

save = make_node("on_save", node_id="f1", kind="function", blocks=[("print_output", {"value": "1"})])
other = ui_node.make_ui_node("Settings", "ui2", UITree.new(pack.id, root_type="popup", root_name="root",
                             props=pack.defaults("popup"), is_container=pack.is_container))
nodes = {"f1": save, "ui2": other}
look = nodes.get

check("no events: no rows", ui_node.event_rows(node, pack, look) == [])

tree.set_event(b1, "command", "f1")
tree.set_event(b2, "command", "ui2")
ui_node.store_tree(node, tree)
rows = ui_node.event_rows(node, pack, look)
check("two linked events give two rows", len(rows) == 2)
r = rows[0]
check("row: widget, event and the pack's wording", (r["widget"], r["event"], r["label"]) == (tree.find(b1)["name"], "command", "On click"))
check("row: the function node is found", r["handler"] is save and r["handler_id"] == "f1" and not r["is_window"])
check("row: a popup window is marked as a window", rows[1]["handler"] is other and rows[1]["is_window"])
check("rows follow the tree order (frame's button first)", rows[0]["widget"] == tree.find(b1)["name"] and rows[1]["widget"] == tree.find(b2)["name"])

tree.set_event(b1, "command", "gone")
ui_node.store_tree(node, tree)
rows = ui_node.event_rows(node, pack, look)
check("a link to a deleted function is still listed", rows[0]["handler"] is None and rows[0]["handler_id"] == "gone" and not rows[0]["is_window"])
check("no pack: still lists the rows, with the key as label", ui_node.event_rows(node, None, look)[0]["label"] == "command")
check("a node without a UI has none", ui_node.event_rows({"name": "x"}, pack, look) == [])
check("not a dict is fine", ui_node.event_rows(None, pack, look) == [])
print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
