"""Tabs (ttk.Notebook): a frame added into it becomes a tab page with a title, the code adds the page, it reads back,
the paper shows one page at a time, and a widget dropped on the notebook becomes a page. Pure, no Tk."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_parse, ui_pack, ui_paper
import ui_designer_model as M
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs", "python")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

pack, _n = ui_pack.load_pack(os.path.join(ROOT, "tkinter"))
t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
nb = M.add_widget(t, pack, "notebook")
p1 = M.add_widget(t, pack, "frame", selected_id=nb)
p2 = M.add_widget(t, pack, "frame", selected_id=nb)
btn = M.add_widget(t, pack, "button", selected_id=p1)
lab = M.add_widget(t, pack, "label", selected_id=p2)
check("a frame in the notebook is a tab page", t.find(p1)["layout"] == {"manager": "tab", "text": "Tab 1"} and t.find(p2)["layout"]["text"] == "Tab 2")
check("a button in a page is placed normally", t.find(btn)["layout"]["manager"] == "place")
check("the notebook's children may only be tabs", pack.layouts_for("notebook") == ["tab"] and "tab" not in pack.layouts_for("frame"))
check("a tree with tabs has no problems", pack.tree_problems(t) == [])

t.find(p2)["layout"]["text"] = "Settings"
node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
text, _p = ui_node.generate_text(node, pack, lambda _i: None)
nbn, n1, n2 = (t.find(i)["name"] for i in (nb, p1, p2))
check("the notebook is created", f"{nbn} = ttk.Notebook(root)" in text)
check("each page is added with its title", f"{nbn}.add({n1}, text='Tab 1')" in text and f"{nbn}.add({n2}, text='Settings')" in text)
tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
check(f"it reads back ({probs})", tree is not None and [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()])
if tree is not None:
    pg = [c for c in next(n for n in tree.walk() if n["type"] == "notebook")["children"]]
    check("... with the titles", [c["layout"] for c in pg] == [{"manager": "tab", "text": "Tab 1"}, {"manager": "tab", "text": "Settings"}])

# which page the paper shows
check("first page by default", M.hidden_tabs(t, None) == {p2})
check("a click on the second tab", M.hidden_tabs(t, {nb: p2}) == {p1})
check("selecting a widget inside a page shows that page", M.hidden_tabs(t, {nb: p1}, sel=lab) == {p1})
paper = ui_paper.Paper(t, pack)
boxes = paper.boxes(560, 380, skip=M.hidden_tabs(t, None))
ids = {b["id"] for b in boxes}
check("the paper draws one page and its widgets only", p1 in ids and btn in ids and p2 not in ids and lab not in ids)
nbb = next(b for b in boxes if b["id"] == nb); pgb = next(b for b in boxes if b["id"] == p1)
check("the page sits under the row of tabs and fills the notebook", pgb["y"] == nbb["y"] + ui_paper.TAB_STRIP and pgb["w"] == nbb["w"] and pgb["h"] == nbb["h"] - ui_paper.TAB_STRIP)

# a widget from outside dropped on the row of tabs becomes a page
outside = M.add_widget(t, pack, "label")
paper = ui_paper.Paper(t, pack)
boxes = paper.boxes(560, 380, skip=M.hidden_tabs(t, None))
nbb = next(b for b in boxes if b["id"] == nb)
ch = M.move_changes(t, paper, boxes, outside, nbb["x"] + 10, nbb["y"] + 2, 40, 16, pack)
check("dropped on the tabs it becomes a tab page", ch.get(outside, {}).get("parent") == nb and ch[outside]["layout"]["manager"] == "tab")

# other libraries are untouched
for lib in ("customtkinter", "kivy"):
    other, _ = ui_pack.load_pack(os.path.join(ROOT, lib))
    check(f"{lib}: layouts_for gives every layout", other.layouts_for("frame") == [m for m, spec in other.layouts.items() if not spec.get("child_only")])

print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
