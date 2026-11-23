"""Hand-written Kivy code read into the designer (pure, no Tk; kivy itself is stubbed)."""
import os, sys
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import ui_pack, ui_import_reader, ui_gen
from kivy_stub import stub_kivy

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

PACK, _ = ui_pack.load_pack(os.path.join(HERE, "..", "ui_packs", "python", "kivy"))

SRC = '''
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

TOTAL = 0

class CalcApp(App):
    title = "Calc"
    def build(self):
        root = BoxLayout(orientation='vertical', padding=10)
        self.display = Label(text='0', font_size=40, size_hint_y=None, height=80)
        root.add_widget(self.display)
        grid = GridLayout(cols=3)
        for n in range(3):
            grid.add_widget(Button(text=str(n)))
        grid.add_widget(Button(text='C', on_press=self.clear, background_color=(1, 0, 0, 1)))
        entry = TextInput(multiline=False, hint_text='x')
        root.add_widget(grid)
        root.add_widget(entry)
        entry.bind(text=self.changed)
        return root
    def clear(self, instance):
        self.display.text = '0'
    def changed(self, instance, value):
        print(value)

CalcApp().run()
'''

def by_name(tree):
    return {n["name"]: n for n in tree.walk()}

def main():
    # ---- the new layouts in the pack
    check("kivy pack loads clean with grid and box frames", PACK is not None and {"gridframe", "boxframe"} <= set(PACK.widgets) and "cell" in PACK.layouts)
    check("their children use 'cell', a plain frame's use 'place'", PACK.layouts_for("boxframe") == ["cell"] and PACK.layouts_for("gridframe") == ["cell"] and PACK.layouts_for("frame") == ["place"])

    r = ui_import_reader.read(SRC, PACK)
    check("a Kivy class is read", r.tree is not None and not r.problems and r.widgets == 5)
    w = by_name(r.tree)
    check("title and window", r.tree.root["props"]["title"] == "Calc" and r.tree.root["type"] == "window")
    check("a returned BoxLayout sits in the window", w["root"]["type"] == "boxframe" and w["root"]["props"] == {"orientation": "vertical", "padding": 10})
    check("fixed height in a box becomes the cell layout", w["display"]["layout"] == {"manager": "cell", "height": 80} and w["display"]["props"] == {"text": "0", "font_size": 40})
    check("GridLayout with its columns", w["grid"]["type"] == "gridframe" and w["grid"]["props"] == {"cols": 3})
    check("TextInput(multiline=False) is an entry", w["entry"]["type"] == "entry" and w["entry"]["props"] == {"hint_text": "x"})
    check("an unknown option stays as written", w["button"]["extra"] == {"background_color": "(1, 0, 0, 1)"})
    check("event links: on_press= and .bind()", ("button", "press", "clear") in r.links and ("entry", "text", "changed") in r.links)
    check("the loop that makes buttons stays as code", any("for n in range(3)" in s for s in r.tree.extra["post_code"]))
    check("methods become plain functions; self.display became display", "def clear(instance):" in r.before and "display.text = '0'" in r.before and "self" not in r.before)
    check("the .run() call is left to the generated program", ".run()" not in r.before + r.after and "TOTAL = 0" in r.before)

    # the program still runs and does the same (kivy stubbed)
    for name, key, fn in r.links:
        r.tree.find(w[name]["id"])["events"][key] = fn
    gen = ui_gen.generate(r.tree, PACK, handler_name=lambda t: t)
    text = "\n\n".join([r.before, ui_gen.render(gen)])
    mods, App = stub_kivy()
    ns = {}
    with mock.patch.dict(sys.modules, mods):
        exec(compile(text, "<ui>", "exec"), ns)
    ui = ns["ui"]
    check("the generated program builds the same tree", ui.root_window.children == [ui.root] and ui.root.children == [ui.display, ui.grid, ui.entry] and len(ui.grid.children) == 4 and ui.button in ui.grid.children)   # the loop's 3 buttons ran too (after it: they are kept after the widgets)
    check("handlers reach widgets by name", ns["display"].text == "0" and App.ran is not None)

    # ---- refusals
    bad = ui_import_reader.read("from kivy.app import App\nclass A(App):\n    x = 1\n    def build(self):\n        return None\n", PACK)
    check("class attributes are refused with a reason", bad.tree is None and bad.problems)
    kv = ui_import_reader.read("from kivy.lang import Builder\nclass A(App):\n    def build(self):\n        return Builder.load_string('x')\n", PACK)
    check("kv is said not to be read", kv.tree is None and any(".kv" in p for p in kv.problems))
    plain = ui_import_reader.read("from kivy.app import App\nfrom kivy.uix.relativelayout import RelativeLayout\nfrom kivy.uix.button import Button\nclass A(App):\n    def build(self):\n        r = RelativeLayout()\n        r.add_widget(Button(text='x', size=(80, 30)))\n        return r\n", PACK)
    pw = by_name(plain.tree) if plain.tree else {}
    check("a RelativeLayout is the window; a child's size becomes width/height", plain.tree is not None and pw["button"]["layout"] == {"manager": "place", "x": 0, "y": 0, "width": 80, "height": 30})

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
