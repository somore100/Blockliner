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

class Calls:
    """Stands in for the `ui` namespace: remembers every call."""
    def __init__(self, answer=None):
        self.calls, self.answer = [], answer
    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            return self.answer
        return call

def run(code, answer=None):
    ui = Calls(answer)
    ns = {"ui": ui}
    exec(code, ns)
    return ns, ui.calls

def render(file, **values):
    return renderer.render_template(block(file)["template"], values)

code = render("ui_set_text.json", widget="label", text="\"Hi\"")
check("set text: the code", code == "ui.set_text('label', \"Hi\")\n")
check("set text: it asks the window to set the text", run(code)[1] == [("set_text", ("label", "Hi"))])

code = render("ui_set_option.json", widget="button", option="state", value="\"disabled\"")
check("set option: it asks the window", run(code)[1] == [("set_option", ("button", "state", "disabled"))])
check("set option: the option list comes from the UI library", block("ui_set_option.json")["params"][1]["choices"] == "@ui_options")

code = render("ui_read_input.json", variable="name", widget="entry")
ns, calls = run(code, answer="Ann")
check("read input: puts the text in the variable", ns["name"] == "Ann" and calls == [("get_text", ("entry",))])

for f, vals, expect in (
        ("ui_set_enabled.json", {"widget": "b", "enabled": "False"}, ("set_enabled", ("b", False))),
        ("ui_set_value.json", {"widget": "s", "value": "30"}, ("set_value", ("s", 30))),
        ("ui_move_widget.json", {"widget": "b", "x": "5", "y": "9"}, ("move_widget", ("b", 5, 9))),
        ("ui_resize_widget.json", {"widget": "b", "width": "120", "height": "40"}, ("resize_widget", ("b", 120, 40)))):
    check(f"{f}: renders the call", run(render(f, **vals))[1] == [expect])
ns, calls = run(render("ui_read_value.json", variable="v", widget="s"), answer=7)
check("read value: puts the value in the variable", ns["v"] == 7 and calls == [("get_value", ("s",))])

ACTIONS = ("set_text", "get_text", "set_enabled", "set_value", "get_value", "move_widget", "resize_widget", "set_option")
for p in packs:
    defined = [ln.split("(")[0][4:] for ln in p.actions if ln.startswith("def ")]
    check(f"{p.id}: defines every action the blocks use ({defined})", all(a in defined for a in ACTIONS))
    check(f"{p.id}: offers option names", bool(p.options))

for f in ("ui_set_text.json", "ui_set_option.json", "ui_read_input.json", "ui_set_enabled.json", "ui_set_value.json", "ui_read_value.json", "ui_move_widget.json", "ui_resize_widget.json"):
    d = block(f)
    check(f"{f}: GUI category, has a description", d["category"] == "GUI" and d["description"])
    widgets = [p for p in d["params"] if p["name"] == "widget"]
    check(f"{f}: the widget parameter is a dropdown of the window's widgets", widgets and widgets[0]["choices"] == "@ui_widgets")

for f, key, kind in (("ui_show_widget.json", "widget", "@ui_widgets"), ("ui_hide_widget.json", "widget", "@ui_widgets"), ("ui_show_screen.json", "screen", "@ui_screens")):
    d = block(f)
    ps = [p for p in d["params"] if p["name"] == key]
    check(f"{f}: GUI category and a dropdown of {kind}", d["category"] == "GUI" and ps and ps[0]["choices"] == kind)
b = block("ui_show_widget.json")
check("show widget: renders a call on the UI namespace", renderer.render_template(b["template"], {"widget": "btn"}) == "ui.show_widget('btn')\n")
check("hide widget: renders", renderer.render_template(block("ui_hide_widget.json")["template"], {"widget": "btn"}) == "ui.hide_widget('btn')\n")
check("show screen: renders", renderer.render_template(block("ui_show_screen.json")["template"], {"screen": "home"}) == "ui.show_screen('home')\n")

# --- the language pack still loads and keeps the dropdown definitions -------------------
from engine import loader
blocks = loader.load_language_pack(os.path.join(ROOT, "languages", "python"))[1]
check("pack: the new blocks load", isinstance(blocks, dict) and all(k in blocks for k in ("ui_set_text", "ui_set_option", "ui_read_input")))
if isinstance(blocks, dict) and "ui_set_text" in blocks:
    check("pack: 'choices' survives loading", blocks["ui_set_text"]["params"][0].get("choices") == "@ui_widgets")

print("ALL OK" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
