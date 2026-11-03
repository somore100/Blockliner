"""The designer reaches Code Builder's document only through codebuilder_api
(pure: reads source text, and drives the facade with a fake app)."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from codebuilder_api import CodeBuilderFacade
from nodes_model import make_node

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

def read(name):
    return open(os.path.join(HERE, "..", name), encoding="utf-8").read()

def strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))

# The editor is a component: it must not know the app, tabs, or Code Builder.
ed = read("designer_editor.py")
ed_code = strip_comments(ed)
for banned in ("self.tabs", "active_tab_index", "get_active_node", "iter_tab_nodes", "ui_pack_for",
               "workspace_canvas", "workspace_frame", "workspace_scrollbar", "project_blocks",
               "_workspace_locked", "view_mode", "designer_node", "self.cb", "make_node"):
    check(f"editor does not use {banned}", banned not in ed_code)
for module in ("ui", "ui_tabs", "ui_layers", "ui_canvas", "ui_node", "ui_parse", "codebuilder_api", "nodes_model"):
    check(f"editor does not import {module}",
          not re.search(rf"^\s*(import {module}\b|from {module} import)", ed, re.M))
check("port needs no Tk", not re.search(r"^\s*(import|from)\s+tkinter", read("designer_port.py"), re.M))

src = read("ui_designer.py")
code = strip_comments(src)

for banned in ("self.tabs", "active_tab_index", "get_active_node", "iter_tab_nodes", "ui_pack_for",
               "get_raw_code", "_ui_handler_resolver", "regenerate_ui_nodes", "update_generated_code",
               "mark_active_tab_dirty", "_ui_last_blocks", "project_blocks", "make_node"):
    check(f"adapter does not use {banned}", banned not in code)
check("adapter imports the facade", "from codebuilder_api import" in src)

facade_src = open(os.path.join(HERE, "..", "codebuilder_api.py"), encoding="utf-8").read()
check("facade needs no Tk", not re.search(r"^\s*(import|from)\s+tkinter", facade_src, re.M))


class FakeApp:
    def __init__(self):
        self.nodes = [make_node("main", node_id="m", blocks=[("raw", {"code": "a"}), ("raw", {"code": "b"})]),
                      make_node("go", node_id="g", blocks=[]),
                      make_node("K", node_id="k", kind="class", child_nodes=[make_node("inner", node_id="i", blocks=[])])]
        self.tabs = [{"language": "python", "nodes": self.nodes}]
        self.active_tab_index = 0
        self.view_mode = "node"
        self.dirty = 0
        self.regenerated = 0
    def get_active_node(self, tab): return tab["nodes"][0]
    def ui_pack_for(self, lang): return f"pack:{lang}"
    def iter_tab_nodes(self, tab):
        def walk(ns, path):
            for n in ns:
                yield n, path
                yield from walk(n.get("child_nodes", []), path + [n["name"]])
        return walk(tab["nodes"], [])
    def _ui_handler_resolver(self, tab): return lambda i: None
    def get_raw_code_block_id(self, lang): return "raw"
    def get_raw_code_param_name(self, bid): return "code"
    def mark_active_tab_dirty(self): self.dirty += 1
    def regenerate_ui_nodes(self): self.regenerated += 1
    def update_generated_code(self): self.regenerated += 10


app = FakeApp()
cb = CodeBuilderFacade(app)
check("available", cb.available() and cb.in_node_view())
check("language and pack", cb.language() == "python" and cb.ui_pack() == "pack:python")
node, pack = cb.context()
check("context", node["id"] == "m" and pack == "pack:python")
check("function nodes exclude one and skip classes",
      [n["name"] for n in cb.function_nodes(exclude=node)] == ["go", "inner"])
check("raw code joins blocks", cb.raw_code_text(node) == "a\nb")
node["blocks"].append(("other", {}))
check("raw code is None for mixed blocks", cb.raw_code_text(node) is None)
check("raw code is None when empty", cb.raw_code_text(app.nodes[1]) is None)
first = cb.add_function_node("on_btn_command")
second = cb.add_function_node("on_btn_command")
names = [n["name"] for n, _p in app.iter_tab_nodes(app.tabs[0])]
check("handler nodes are unique", "on_btn_command" in names and "on_btn_command_2" in names and first != second)
check("odd names become identifiers", cb.add_function_node("on_my btn-x_c") and "on_my_btn_x_c" in
      [n["name"] for n, _p in app.iter_tab_nodes(app.tabs[0])])
cb.mark_dirty(); cb.regenerate()
check("mark_dirty and regenerate reach the app", app.dirty == 1 and app.regenerated == 11)
cb.forget_generated(node)
app.view_mode = "file"
check("view mode follows the app", not cb.in_node_view())

print("ALL OK" if not fails else f"FAILURES: {fails}")
