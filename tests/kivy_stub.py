"""A stand-in for the parts of kivy the generated UI code uses (shared by the Kivy tests; not a test itself)."""
import types


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
