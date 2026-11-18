"""Scrollbars (vertical / horizontal) that link to the widget they scroll, and the table (Treeview): generated code,
the link lines only when a target is set, reading the code back, and running against a stub tkinter. Pure, no Tk."""
import os, sys, types
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_parse, ui_pack
import ui_designer_model as M
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs", "python", "tkinter")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

pack, notes = ui_pack.load_pack(ROOT)
t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
lst = M.add_widget(t, pack, "listbox")
vbar = M.add_widget(t, pack, "scrollbar")
hbar = M.add_widget(t, pack, "hscrollbar")
tbl = M.add_widget(t, pack, "treeview")
name = lambda i: t.find(i)["name"]

def gen():
    node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
    return node, ui_node.generate_text(node, pack, lambda _i: None)[0]

node, text = gen()
check("no target: no link lines", "yscrollcommand" not in text and "xscrollcommand" not in text and ".yview" not in text)
check("the vertical scrollbar says vertical", f"{name(vbar)} = ttk.Scrollbar(root, orient='vertical')" in text)
tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
check(f"no target: reads back with the right types ({probs})", tree is not None and
      [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()])

t.find(vbar)["props"]["target"] = name(lst)
t.find(hbar)["props"]["target"] = name(tbl)
node, text = gen()
check("vertical link: scrollcommand and command", f"{name(lst)}.configure(yscrollcommand={name(vbar)}.set)" in text and
      f"{name(vbar)}.configure(command={name(lst)}.yview)" in text)
check("horizontal link uses x", f"{name(tbl)}.configure(xscrollcommand={name(hbar)}.set)" in text and
      f"{name(hbar)}.configure(command={name(tbl)}.xview)" in text)
check("the link comes after the target is made", text.index(f"{name(lst)} = ") < text.index(f"{name(lst)}.configure(yscrollcommand"))
tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
check(f"with targets: reads back ({probs})", tree is not None)
if tree is not None:
    check("... the targets and types come back", [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()] and
          sorted(n["props"].get("target") for n in tree.walk() if n["type"] in ("scrollbar", "hscrollbar")) == sorted([name(lst), name(tbl)]))

t.find(tbl)["props"]["columns"] = ["id", "file", "size"]
node, text = gen()
check("table: columns and a heading for each", "columns=['id', 'file', 'size']" in text and "heading(_c, text=_c)" in text)
tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
check(f"table: reads back with its columns ({probs})", tree is not None and
      next(n for n in tree.walk() if n["type"] == "treeview")["props"]["columns"] == ["id", "file", "size"])

tk, ttk = mock.MagicMock(name="tkinter"), mock.MagicMock(name="ttk")
tk.ttk = ttk
with mock.patch.dict(sys.modules, {"tkinter": tk, "tkinter.ttk": ttk}):
    ns = {}
    try:
        exec(compile(text.replace("ui.root.mainloop()", ""), "<generated>", "exec"), ns)
        ran = True
    except Exception as e:
        print("   ", repr(e)); ran = False
check("the code compiles and runs against a stub tkinter", ran)

print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
