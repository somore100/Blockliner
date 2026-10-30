"""UI builder code generator: golden text, executed with a stub tkinter. Pure."""
import json, os, sys, tempfile, types
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_gen, ui_pack
from ui_tree import UITree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

GOLDEN = """import tkinter as tk
from tkinter import ttk
import types

def build_main():
    app = tk.Tk()
    app.title('My app')
    app.geometry('400x300')
    frame = ttk.Frame(app)
    frame.grid(row=0, column=0, sticky='nsew')
    label = ttk.Label(frame, text='Name:')
    label.grid(row=0, column=0)
    entry_name = ttk.Entry(frame, width=20)
    entry_name.grid(row=0, column=1)
    btn_save = tk.Button(app, text='Save', state='disabled', font='{Segoe UI} 14 bold', foreground='#ff0000')
    btn_save.place(x=10, y=50)
    btn_save.configure(command=on_save)
    combobox = ttk.Combobox(app, values=['a', 'b'])
    combobox.grid(row=1, column=0)
    return types.SimpleNamespace(app=app, frame=frame, label=label, entry_name=entry_name, btn_save=btn_save, combobox=combobox)

ui = build_main()
ui.app.mainloop()
"""

def sample(pack):
    t = UITree.new("python/tkinter", props=pack.defaults("window"), root_name="app")
    r = t.root["id"]
    fr = t.add(r, "frame", layout={"manager": "grid", "row": 0, "column": 0, "sticky": "nsew"})
    t.add(fr, "label", props={"text": "Name:"}, layout={"manager": "grid", "row": 0, "column": 0})
    t.add(fr, "entry", name="entry_name", props={"width": 20, "state": "normal"}, layout={"manager": "grid", "row": 0, "column": 1})
    b = t.add(r, "button", name="btn_save", props={"text": "Save", "state": "disabled", "font": "{Segoe UI} 14 bold", "foreground": "#ff0000"}, layout={"manager": "place", "x": 10, "y": 50})
    t.set_event(b, "command", "fn1")
    t.add(r, "combobox", props={"values": ["a", "b"]}, layout={"manager": "grid", "row": 1, "column": 0})
    return t

def main():
    pack, notes = ui_pack.load_pack(os.path.join(ROOT, "python", "tkinter"))
    t = sample(pack)
    res = ui_gen.generate(t, pack, handler_name={"fn1": "on_save"}.get, function_name="build_main")
    text = ui_gen.render(res)
    check("golden text for the sample UI", text == GOLDEN)
    check("no problems for a good tree", res["problems"] == [])
    check("deterministic", ui_gen.render(ui_gen.generate(t, pack, {"fn1": "on_save"}.get, "build_main")) == text)
    check("render without run drops the mainloop", "mainloop" not in ui_gen.render(res, include_run=False))
    check("default function name comes from the root name", ui_gen.generate(t, pack)["function"][0] == "def build_app():")
    check("custom ui variable name", ui_gen.generate(t, pack, ui_name="gui")["call"] == ["gui = build_app()"]
          and ui_gen.generate(t, pack, ui_name="gui")["run"] == ["gui.app.mainloop()"])
    check("omit_when: state normal is left out, disabled is kept", "state='normal'" not in text and "state='disabled'" in text)
    check("inline props never appear as arguments", "title=" not in text and "geometry=" not in text)

    # ---- run the generated code against a stub tkinter
    stub_tk = types.ModuleType("tkinter")
    stub_ttk = types.ModuleType("tkinter.ttk")
    stub_tk.Tk, stub_tk.Text, stub_tk.Listbox = mock.MagicMock(name="Tk"), mock.MagicMock(), mock.MagicMock()
    stub_tk.Button = mock.MagicMock(name="Button")
    for n in ("Frame", "Label", "Button", "Checkbutton", "Entry", "Combobox"):
        setattr(stub_ttk, n, mock.MagicMock(name=n))
    stub_tk.ttk = stub_ttk
    ns = {"on_save": lambda: None}
    with mock.patch.dict(sys.modules, {"tkinter": stub_tk, "tkinter.ttk": stub_ttk}):
        try:
            exec(compile(text, "<generated>", "exec"), ns)
            ran = True
        except Exception as e:
            print("   ", repr(e)); ran = False
    check("generated code compiles and runs", ran)
    ui = ns.get("ui")
    check("returns every widget in a namespace", ui is not None and {"app", "frame", "label", "entry_name", "btn_save", "combobox"} <= set(vars(ui)))
    stub_tk.Button.assert_called_once_with(ui.app, text="Save", state="disabled", font="{Segoe UI} 14 bold", foreground="#ff0000")
    ui.btn_save.configure.assert_called_with(command=ns["on_save"])
    ui.entry_name.grid.assert_called_with(row=0, column=1)
    check("constructors and layout got the right arguments", True)
    ui.app.mainloop.assert_called_once_with()
    check("mainloop was started on the root", True)

    # ---- problems, never exceptions
    t2 = UITree.new("python/tkinter", props={"title": "x"})
    t2.add(t2.root["id"], "mystery")
    nb = t2.add(t2.root["id"], "button")
    t2.set_event(nb, "command", "gone")
    res2 = ui_gen.generate(t2, pack, handler_name=lambda i: None)
    check("unknown widget skipped and reported", "mystery" not in "\n".join(res2["function"]) and any("unknown widget type" in p for p in res2["problems"]))
    check("unplaced widget reported", any("no layout manager" in p for p in res2["problems"]))
    check("unresolvable handler skipped and reported", "command=" not in "\n".join(res2["function"]) and any("can't be found" in p for p in res2["problems"]))
    check("no handler resolver at all is the same", any("can't be found" in p for p in ui_gen.generate(t2, pack)["problems"]))

    # ---- literals and filling
    check("python literals", [ui_gen.literal(k, v) for k, v in (("string", "it's"), ("int", 3), ("bool", True), ("bool", False), ("float", 1.5), ("list", ["a", 2]), ("code", "x+1"), ("string", None))]
          == ["\"it's\"", "3", "True", "False", "1.5", "['a', 2]", "x+1", "None"])
    check("json literals", [ui_gen.literal(k, v, "json") for k, v in (("string", "a\"b"), ("bool", True), ("list", ["a"]), ("string", None), ("code", "raw"))]
          == ['"a\\"b"', "true", '["a"]', "null", "raw"])
    check("plain values", ui_gen.plain(None) == "" and ui_gen.plain(["a", 1]) == "a, 1" and ui_gen.plain(5) == "5")
    check("fill: plain vs !r", ui_gen.fill("{a} {a!r}", {"a": ("x", "'x'")}) == "x 'x'")

    # ---- a second pack: json quoting, code_raw, multi-line templates, other function shape
    tmp = tempfile.mkdtemp()
    folder = os.path.join(tmp, "toy", "toy")
    os.makedirs(os.path.join(folder, "widgets"))
    data = {"format": "blockliner-ui-pack", "version": 1, "id": "toy/toy", "language": "toy", "imports": ["use ui", "use ui"],
            "header": ["use more"], "root_types": ["win"], "quote": "json", "run": "run({ui}.{root})",
            "function": {"def": "fn {fname}() {{", "indent": "\t", "ret": "return [{pairs}]", "pair": "{name}", "call": "let {ui} = {fname}()"},
            "layouts": {"flow": {"props": [{"key": "gap", "kind": "int"}], "code": "{parent}.add({name}, {args})"}},
            "widgets": [{"type": "win", "container": True, "code": ["let {name} = Win()", "{name}.size(1)"], "props": []},
                        {"type": "lbl", "props": [{"key": "text", "kind": "string", "default": "x", "inline": True}, {"key": "on", "kind": "bool", "arg": "enabled"}],
                         "code": "let {name} = Label({text!r}{opts})"},
                        {"type": "raw", "code_raw": "// custom for {name} in {parent}\nraw()"}]}
    with open(os.path.join(folder, "pack.json"), "w") as f: json.dump(data, f)
    toy, tn = ui_pack.load_pack(folder)
    check("toy pack loads", toy is not None and tn == [])
    tt = UITree.new("toy/toy", root_type="win", root_name="w")
    tt.add(tt.root["id"], "lbl", name="a", props={"text": "hi \"there\"", "on": True}, layout={"manager": "flow", "gap": 4})
    tt.add(tt.root["id"], "raw", name="r", layout={"manager": "flow"})
    out = ui_gen.render(ui_gen.generate(tt, toy, function_name="mk"))
    want = ("use ui\nuse more\n\n"
            "fn mk() {\n\tlet w = Win()\n\tw.size(1)\n"
            "\tlet a = Label(\"hi \\\"there\\\"\", enabled=true)\n\tw.add(a, gap=4)\n"
            "\t// custom for r in w\n\traw()\n\tw.add(r, )\n\treturn [w, a, r]\n\n"
            "let ui = mk()\nrun(ui.w)\n")
    check("another language shape: json quoting, arg rename, indent, call and run", out == want or print(repr(out)))
    check("imports deduplicated", out.splitlines()[:2] == ["use ui", "use more"])

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
