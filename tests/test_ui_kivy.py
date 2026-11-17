"""The Kivy UI pack: code generated for it is valid, reads back (screens included), and runs against a stand-in for
kivy (real Kivy isn't needed or installed for this test; the output was not run on real Kivy by this test)."""
import os, sys, types
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_parse, ui_pack
import ui_designer_model as M
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

class Widget:
    """Just enough of a kivy widget: remembers its children, size, position, opacity and what is bound."""
    def __init__(self, *a, **kw):
        self.children, self.opacity, self.disabled, self.height, self.pos, self.size = [], 1, False, 300, (0, 0), (0, 0)
        self.size_hint = (1, 1)
        for k, v in kw.items():
            setattr(self, k, v)
    def add_widget(self, w): self.children.append(w)
    def bind(self, **kw): self.bound = kw

def stub_kivy():
    mods = {}
    def mod(name, **attrs):
        m = types.ModuleType(name); m.__dict__.update(attrs); mods[name] = m
    class App:
        def run(self): App.ran = self
    mod("kivy"); mod("kivy.app", App=App); mod("kivy.core"); mod("kivy.core.window", Window=types.SimpleNamespace(size=(0, 0)))
    mod("kivy.uix")
    for path, cls in (("relativelayout", "RelativeLayout"), ("label", "Label"), ("button", "Button"), ("togglebutton", "ToggleButton"),
                      ("checkbox", "CheckBox"), ("switch", "Switch"), ("textinput", "TextInput"), ("spinner", "Spinner"),
                      ("slider", "Slider"), ("progressbar", "ProgressBar"), ("image", "Image")):
        mod("kivy.uix." + path, **{cls: type(cls, (Widget,), {})})
    return mods, App

def main():
    pack, notes = ui_pack.load_pack(os.path.join(ROOT, "python", "kivy"))
    check(f"loads with no notes {notes}", pack is not None and not notes)
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    lbl = M.add_widget(t, pack, "label")
    M.add_widget(t, pack, "button")
    a = M.add_widget(t, pack, "frame"); b = M.add_widget(t, pack, "frame")
    M.add_widget(t, pack, "togglebutton", selected_id=a)
    M.add_widget(t, pack, "label", selected_id=b)
    t.set_screen(a); t.set_screen(b)
    node = ui_node.make_ui_node("UI 1", "u1", t, order=1)
    text, _p = ui_node.generate_text(node, pack, lambda _i: None)
    compile(text, "<ui>", "exec")
    check("children are added to their parent and placed", "root.add_widget(label)" in text and "place(root, label" in text)
    tree, probs = ui_parse.read_back(node, pack, text, lambda _i: None, lambda _n: None)
    check(f"reads back with its screens {probs}", tree is not None and tree.screens() == ["frame", "frame_2"]
          and [n["type"] for n in tree.walk()] == [n["type"] for n in t.walk()])

    mods, App = stub_kivy()
    ns = {}
    with mock.patch.dict(sys.modules, mods):
        exec(compile(text, "<ui>", "exec"), ns)
    ui = ns["ui"]
    check("the app was started with the window as root", getattr(App, "ran", None) is not None and App.ran.ui_root is ui.root)
    check("widgets are children of their parents", ui.label in ui.root.children and ui.togglebutton in ui.frame.children)
    check("a placed widget has a fixed size and position", ui.label.size_hint == (None, None) and ui.label.pos[0] == 10)
    check("first screen visible, second hidden at start", ui.frame.opacity == 1 and ui.frame_2.opacity == 0 and ui.frame_2.disabled)
    ui.show_screen("frame_2")
    check("show_screen switches", ui.frame.opacity == 0 and ui.frame_2.opacity == 1 and not ui.frame_2.disabled)
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
