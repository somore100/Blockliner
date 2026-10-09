"""Auto-close brackets/quotes. Run under Xvfb."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import code_autoclose as A

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

root = tk.Tk()
def mk(text="", at="end-1c"):
    w = tk.Text(root); w.pack(); w.insert("1.0", text); w.mark_set("insert", at); return w
def key(w, ch, state=0, enabled=True):
    r = A.on_keypress(w, types.SimpleNamespace(char=ch, state=state), enabled)
    if r is None and ch:                      # what Tk's default would do
        w.insert("insert", ch)
    return r
def bs(w, enabled=True):
    r = A.on_backspace(w, types.SimpleNamespace(char="\x08", state=0), enabled)
    if r is None: w.delete("insert-1c", "insert")
    return r
def val(w): return w.get("1.0", "end-1c")
def col(w): return int(w.index("insert").split(".")[1])

w = mk(); key(w, "(")
check("( -> () caret between", val(w) == "()" and col(w) == 1)
key(w, "x"); key(w, ")")
check("typing ) steps over the closer", val(w) == "(x)" and col(w) == 3)
for o, c in (("[", "]"), ("{", "}"), ('"', '"')):
    w = mk(); key(w, o); check(f"{o} pairs", val(w) == o + c and col(w) == 1)
w = mk(); key(w, '"'); key(w, "a"); key(w, '"')
check('closing " steps over', val(w) == '"a"' and col(w) == 3)
w = mk("don"); key(w, "'")
check("apostrophe after a letter stays single", val(w) == "don'")
w = mk("print"); key(w, "(")
check("( after a word pairs", val(w) == "print()" and col(w) == 6)
w = mk("foo", at="1.0"); key(w, "(")
check("( right before a word stays single", val(w) == "(foo")
w = mk("abc", at="1.0"); w.tag_add("sel", "1.0", "1.2"); key(w, "(")
check("selection gets wrapped", val(w) == "(ab)c" and col(w) == 4)
w = mk(); key(w, "("); bs(w)
check("backspace in empty pair deletes both", val(w) == "")
w = mk("(x)", at="1.2"); bs(w)
check("backspace in non-empty pair deletes one char", val(w) == "()")
w = mk(); key(w, "("); key(w, "["); key(w, "{")
check("nesting ([{ }])", val(w) == "([{}])" and col(w) == 3)
w = mk(); key(w, "(", enabled=False)
check("disabled: plain char", val(w) == "(")
w = mk(); key(w, "(", state=0x4)
check("Ctrl+( is left alone", val(w) == "(")
w = mk(); key(w, "")
check("no char (arrow/shift): ignored", val(w) == "")
w = mk("''"); w.mark_set("insert", "1.2"); key(w, "'")
check("third quote after '' not paired", val(w) == "'''")
# guard refusing the edit must not move the caret wrongly
w = mk("a b", at="1.1"); orig = w.insert
w.insert = lambda *a, **k: None
r = A.on_keypress(w, types.SimpleNamespace(char="(", state=0), True)
check("refused edit: handled, caret unmoved", r == "break" and col(w) == 1 and val(w) == "a b")
# wired into the real app
from ui import BlocklinerUI
app = BlocklinerUI(initial_lang="python", languages_path="languages"); app.update()
app.save_app_settings = lambda: None      # never touch the real settings file
app.settings["code_autoclose"] = True; app.autoclose_var.set(True)
t = app.code_text
app.settings["code_edit_warned"] = True; app.settings["code_sync_mode"] = "manual"; app.settings["safe_mode"] = False
t.delete("1.0", "end"); t.focus_force(); app.update()
t.event_generate("<KeyPress>", keysym="parenleft"); app.update()
check("real code panel: ( auto-closes", t.get("1.0", "end-1c") == "()")
app.settings["code_autoclose"] = False
t.delete("1.0", "end"); t.event_generate("<KeyPress>", keysym="parenleft"); app.update()
check("setting off in the app: plain (", t.get("1.0", "end-1c") == "(")
check("checkbox exists and starts from the setting", app.autoclose_var.get() is True)
app.autoclose_var.set(False); app.on_autoclose_toggle()
check("toggle writes the setting", app.settings["code_autoclose"] is False)
app.destroy()
print("FAILURES:", FAILURES)
sys.exit(1 if FAILURES else 0)
