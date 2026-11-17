"""Widget actions (set text, read value, enable, move, resize ...) work for each UI library: they are written by the
library's pack into the generated code. tkinter runs for real (needs a display, e.g. Xvfb); customtkinter and kivy
run against stand-ins that behave the way those libraries' widgets do (neither is installed for this test)."""
import os, sys, types
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_node, ui_pack
import ui_designer_model as M
from ui_tree import UITree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kivy_stub import stub_kivy

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def code_for(lib, kinds):
    pack, _ = ui_pack.load_pack(os.path.join(ROOT, "python", lib))
    t = UITree.new(pack.id, props=pack.defaults("window"), is_container=pack.is_container)
    for k in kinds:
        M.add_widget(t, pack, k)
    text, _p = ui_node.generate_text(ui_node.make_ui_node("UI", "u", t, order=1), pack, lambda _i: None)
    return text

def tkinter_run():
    text = code_for("tkinter", ["label", "entry", "text", "combobox", "scale", "progressbar", "checkbutton", "button", "spinbox"])
    for name in ("set_text", "get_text", "set_enabled", "set_value", "get_value", "move_widget", "resize_widget", "set_option"):
        check(f"tkinter: ui.{name} is exposed", f"{name}=" in text.replace(" ", ""))
    ns = {}
    exec(compile(text.replace("ui.root.mainloop()", ""), "<ui>", "exec"), ns)
    ui = ns["ui"]
    ui.root.update()
    ui.set_text("label", "Hi"); ui.set_text("entry", "Ann"); ui.set_text("text", "a\nb"); ui.set_text("combobox", "x")
    check("tkinter: set/get text on a label", ui.get_text("label") == "Hi")
    check("tkinter: set/get text on an entry", ui.get_text("entry") == "Ann")
    check("tkinter: set/get text on a text box", ui.get_text("text") == "a\nb")
    check("tkinter: a combobox", ui.get_text("combobox") == "x")
    ui.set_text("entry", "Bo")
    check("tkinter: set text replaces, not appends", ui.get_text("entry") == "Bo")
    ui.set_value("scale", 3); ui.set_value("progressbar", 40)
    check("tkinter: scale and progress bar values", ui.get_value("scale") == 3 and ui.get_value("progressbar") == 40)
    check("tkinter: a checkbutton starts off", ui.get_value("checkbutton") is False)
    ui.set_value("checkbutton", True)
    check("tkinter: ... and can be turned on", ui.get_value("checkbutton") is True)
    ui.set_enabled("button", False); ui.set_enabled("entry", False)
    check("tkinter: disabling tk and ttk widgets", str(ui.button.cget("state")) == "disabled" and "disabled" in ui.entry.state())
    ui.set_enabled("button"); ui.set_enabled("entry")
    check("tkinter: enabling again", str(ui.button.cget("state")) == "normal" and "disabled" not in ui.entry.state())
    ui.move_widget("button", 30, 40); ui.root.update()
    check("tkinter: move_widget places the widget", ui.button.winfo_manager() == "place" and ui.button.place_info()["x"] == "30" and ui.button.place_info()["y"] == "40")
    ui.resize_widget("button", 120, 50); ui.root.update()
    check("tkinter: resize_widget (placed)", ui.button.winfo_width() == 120 and ui.button.winfo_height() == 50)
    ui.set_option("label", "foreground", "red")
    check("tkinter: set_option", str(ui.label.cget("foreground")) == "red")
    ui.root.destroy()

class Rec:
    """A stand-in widget that records, with the methods of one customtkinter widget."""
    def __init__(self, *a, **kw): self.opts, self.text = dict(kw), ""
    def configure(self, **kw): self.opts.update(kw)
    def cget(self, k): return self.opts.get(k, "")
    def place(self, **kw): self.opts["place"] = kw
    def delete(self, *a): self.text = ""
    def insert(self, _i, t): self.text += t
    def get(self, *a): return self.text
    def set(self, v): self.text = v
    def grid(self, **kw): pass
    def mainloop(self): pass
    def title(self, *a): pass
    def geometry(self, *a): pass

def ctk_run():
    text = code_for("customtkinter", ["label", "entry", "text", "combobox", "scale", "switch", "button"])
    ctk = types.ModuleType("customtkinter")
    for n in ("CTk", "CTkLabel", "CTkEntry", "CTkTextbox", "CTkComboBox", "CTkSlider", "CTkSwitch", "CTkButton", "CTkFrame"):
        cls = type(n, (Rec,), {})
        if n == "CTkSwitch":
            cls.select = lambda self: setattr(self, "text", 1)
            cls.deselect = lambda self: setattr(self, "text", 0)
        setattr(ctk, n, cls)
    ns = {}
    with mock.patch.dict(sys.modules, {"customtkinter": ctk}):
        exec(compile(text.replace("ui.root.mainloop()", ""), "<ui>", "exec"), ns)
    ui = ns["ui"]
    ui.set_text("label", "Hi"); ui.set_text("entry", "Ann"); ui.set_text("text", "t"); ui.set_text("combobox", "c")
    check("customtkinter: labels use configure(text=)", ui.label.opts["text"] == "Hi" and ui.get_text("label") == "Hi")
    check("customtkinter: entry, textbox and combobox have their own ways",
          ui.get_text("entry") == "Ann" and ui.get_text("text") == "t" and ui.get_text("combobox") == "c")
    ui.set_value("scale", 0.5)
    check("customtkinter: slider value", ui.get_value("scale") == 0.5)
    ui.set_value("switch", True)
    check("customtkinter: switch on/off", ui.get_value("switch") is True)
    ui.set_value("switch", False)
    check("customtkinter: ... and off", ui.get_value("switch") is False)
    ui.set_enabled("button", False)
    check("customtkinter: enabled flag", ui.button.opts["state"] == "disabled")
    ui.move_widget("button", 3, 4); ui.resize_widget("button", 90, 30)
    check("customtkinter: move and resize", ui.button.opts["place"] == {"x": 3, "y": 4} and ui.button.opts["width"] == 90)

def kivy_run():
    mods, _App = stub_kivy()
    text = code_for("kivy", ["label", "entry", "scale", "checkbutton", "button"])
    ns = {}
    with mock.patch.dict(sys.modules, mods):
        exec(compile(text, "<ui>", "exec"), ns)
    ui = ns["ui"]
    ui.set_text("label", "Hi")
    check("kivy: text is the widget's text property", ui.label.text == "Hi" and ui.get_text("label") == "Hi")
    ui.set_value("scale", 7); ui.set_value("checkbutton", True)
    check("kivy: value / active", ui.get_value("scale") == 7 and ui.get_value("checkbutton") is True)
    ui.set_enabled("button", False)
    check("kivy: enabled is not disabled", ui.button.disabled is True)
    ui.move_widget("button", 20, 50)
    check("kivy: move counts y from the top", ui.button.pos == (20, ui.root.height - 50 - ui.button.height))
    ui.root.height = 500; ui.root.bound["height"]()
    ui.resize_widget("button", 60, 20)
    check("kivy: resize keeps the spot", ui.button.size == (60, 20) and ui.button.pos[0] == 20)
    ui.set_option("label", "opacity", 0.5)
    check("kivy: set_option sets the property", ui.label.opacity == 0.5)

def main():
    tkinter_run(); ctk_run(); kivy_run()
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)

main()
