"""Menu bar (tk.Menu): menus go in the bar, items in menus, a menu made first gets a bar, items need no placement,
the code reads back with the handlers, and menus are not boxes on the paper. Pure, no Tk."""
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
lab = M.add_widget(t, pack, "label")
file_ = M.add_widget(t, pack, "menu")                      # no bar yet: one is made
bar = t.parent_of(file_)
check("a menu added first gets a menu bar under the window", bar["type"] == "menubar" and t.parent_of(bar["id"])["id"] == t.root["id"])
check("the menu is a titled cascade", t.find(file_)["layout"] == {"manager": "cascade", "text": "Menu 1"})
t.find(file_)["layout"]["text"] = "File"
new = M.add_widget(t, pack, "menuitem", selected_id=file_)
sep = M.add_widget(t, pack, "menusep", selected_id=new)       # selecting an item still adds to its menu
quit_ = M.add_widget(t, pack, "menuitem", selected_id=new)
sub = M.add_widget(t, pack, "menu", selected_id=file_)
check("items and separators go in the menu, with no layout", t.parent_of(sep)["id"] == file_ and t.find(new)["layout"] == {} and t.find(sep)["layout"] == {})
check("a menu inside a menu is a sub-menu", t.parent_of(sub)["id"] == file_)
btn = M.add_widget(t, pack, "button", selected_id=new)
check("an ordinary widget never goes into a menu", t.parent_of(btn)["id"] == t.root["id"])
check("a second menu goes in the same bar", t.parent_of(M.add_widget(t, pack, "menu", selected_id=lab))["id"] == bar["id"])
check("no problems", pack.tree_problems(t) == [])

t.find(new)["props"]["text"] = "New"
t.find(quit_)["props"]["text"] = "Quit"
t.find(quit_)["events"]["click"] = "f1"
node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
text, probs = ui_node.generate_text(node, pack, lambda i: "do_quit" if i == "f1" else None)
bn, fn = t.find(bar["id"])["name"], t.find(file_)["name"]
check(f"the bar is created and set ({probs})", f"{bn} = tk.Menu(root)" in text and f"root.configure(menu={bn})" in text)
check("the menu is created and added", f"{fn} = tk.Menu({bn}, tearoff=0)" in text and f"{bn}.add_cascade(label='File', menu={fn})" in text)
check("items, separator and the handler", f"{t.find(new)['name']} = {fn}.add_command(label='New')" in text
      and f"{fn}.add_separator()" in text and f"{fn}.entryconfigure('Quit', command=do_quit)" in text)
check("no 'won't be placed' problem for items", not any("placed" in p for p in probs))

tree, probs = ui_parse.read_back(node, pack, text, lambda i: "do_quit" if i == "f1" else None, lambda n: "f1" if n == "do_quit" else None)
check(f"it reads back ({probs})", tree is not None and [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()])
if tree is not None:
    q = next(n for n in tree.walk() if n["type"] == "menuitem" and n["props"].get("text") == "Quit")
    check("... with the handler and titles", q["events"].get("click") == "f1" and any(n["layout"].get("text") == "File" for n in tree.walk()))

boxes = ui_paper.Paper(t, pack).boxes(560, 380)
check("menus are not boxes on the paper", not {b["type"] for b in boxes} & {"menubar", "menu", "menuitem", "menusep"})

print("\nFAILED: " + ", ".join(FAILURES) if FAILURES else "\nALL PASS")
sys.exit(1 if FAILURES else 0)
