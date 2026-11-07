"""Widget blocks (set text / set option / read input) and what they need from
the designer: the widget names of a UI node, the text setting a widget lets
you type on the paper, and generated code that actually works against the
window a UI node builds. Pure, no Tk."""
import json, os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_designer_model as dm
import ui_node, ui_pack
from engine import renderer
from ui_tree import UITree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
fails = []
def check(name, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)

packs, _ = ui_pack.find_packs([os.path.join(ROOT, "ui_packs")], "python")
tk_pack = packs[0]

# --- inline text -----------------------------------------------------------------
for wtype, key in (("label", "text"), ("button", "text"), ("checkbutton", "text"), ("window", "title")):
    check(f"inline: {wtype} is typed on the paper as '{key}'", dm.inline_prop(tk_pack, wtype) == key)
for wtype in ("frame", "entry", "listbox", "nosuch"):
    check(f"inline: {wtype} has no text to type", dm.inline_prop(tk_pack, wtype) is None)
for p in packs:
    check(f"inline: {p.id} label works too", dm.inline_prop(p, "label") == "text")

# --- widget names ------------------------------------------------------------------
tree = UITree.new(tk_pack.id, root_type="window", root_name="root", props=tk_pack.defaults("window"),
                  is_container=tk_pack.is_container)
frame = tree.add(tree.root["id"], "frame", props=tk_pack.defaults("frame"))
lab = tree.add(frame, "label", props=tk_pack.defaults("label"))
btn = tree.add(frame, "button", props=tk_pack.defaults("button"))
node = ui_node.make_ui_node("Main", "n1", tree)
names = ui_node.widget_names(node)
check("names: the window comes first", names[0] == "root")
check("names: every widget is listed once", names == ["root", "frame", "label", "button"])
check("names: a node without a UI has none", ui_node.widget_names({"name": "x"}) == [])
check("names: not a dict is fine", ui_node.widget_names(None) == [])

# --- the blocks --------------------------------------------------------------------
def block(name):
    with open(os.path.join(ROOT, "languages", "python", "blocks", name), encoding="utf-8") as f:
        return json.load(f)

class Fake:
    """Stands in for a widget: remembers what was configured."""
    def __init__(self, text=""):
        self.calls, self.text = [], text
    def configure(self, **kw):
        self.calls.append(kw)
    def get(self):
        return self.text

def run(code, **widgets):
    ns = {"ui": types.SimpleNamespace(**widgets)}
    exec(code, ns)
    return ns

b = block("ui_set_text.json")
code = renderer.render_template(b["template"], {"widget": "label", "text": "\"Hi\""})
check("set text: the code", code == "ui.label.configure(text=\"Hi\")\n")
w = Fake(); run(code, label=w)
check("set text: it configures the widget", w.calls == [{"text": "Hi"}])

b = block("ui_set_option.json")
code = renderer.render_template(b["template"], {"widget": "button", "option": "state", "value": "\"disabled\""})
w = Fake(); run(code, button=w)
check("set option: it configures the widget", w.calls == [{"state": "disabled"}])
check("set option: the option list is offered", "state" in b["params"][1]["choices"] and "text" in b["params"][1]["choices"])

b = block("ui_read_input.json")
code = renderer.render_template(b["template"], {"variable": "name", "widget": "entry"})
ns = run(code, entry=Fake("Ann"))
check("read input: puts the text in the variable", ns["name"] == "Ann")

for f in ("ui_set_text.json", "ui_set_option.json", "ui_read_input.json"):
    d = block(f)
    check(f"{f}: GUI category, has a description", d["category"] == "GUI" and d["description"])
    widgets = [p for p in d["params"] if p["name"] == "widget"]
    check(f"{f}: the widget parameter is a dropdown of the window's widgets", widgets and widgets[0]["choices"] == "@ui_widgets")

# --- the language pack still loads and keeps the dropdown definitions -------------------
from engine import loader
blocks = loader.load_language_pack(os.path.join(ROOT, "languages", "python"))[1]
check("pack: the new blocks load", isinstance(blocks, dict) and all(k in blocks for k in ("ui_set_text", "ui_set_option", "ui_read_input")))
if isinstance(blocks, dict) and "ui_set_text" in blocks:
    check("pack: 'choices' survives loading", blocks["ui_set_text"]["params"][0].get("choices") == "@ui_widgets")

print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
