"""Quick layer step keybinds (Up/Down by default), settings capture saves
instantly, bare keys pause in text widgets. Run under Xvfb."""
import os, sys, tkinter as tk
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ui import BlocklinerUI, keybind_from_event, keybind_label
from ui_common import keybind_is_bare, DEFAULT_SETTINGS

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def ev(keysym, state=0):
    return NS(keysym=keysym, state=state)

def main():
    # pure helpers
    check("bare Up accepted", keybind_from_event(ev("Up")) == "Key-Up")
    check("bare F5 accepted", keybind_from_event(ev("F5")) == "Key-F5")
    check("bare letter rejected", keybind_from_event(ev("a")) is None)
    check("Ctrl+Up", keybind_from_event(ev("Up", 0x4)) == "Control-Key-Up")
    check("modifier alone rejected", keybind_from_event(ev("Shift_L", 0x1)) is None)
    check("label Key-Up -> Up", keybind_label("Key-Up") == "Up")
    check("bare detection", keybind_is_bare("Key-Up") and not keybind_is_bare("Control-Key-Up") and not keybind_is_bare("Alt-Key-F1"))
    check("defaults are Up/Down", DEFAULT_SETTINGS["keybinds"]["layer_up"] == "Key-Up" and DEFAULT_SETTINGS["keybinds"]["layer_down"] == "Key-Down")

    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x800+0+0"); app.update(); app.update()
    saved = []
    app.save_app_settings = lambda: saved.append(dict(app.settings.get("keybinds", {})))

    # stepping
    app.goto_layer("files"); app.update()
    app.step_layer(1); app.update()
    check("Files + down -> Nodes", app.view_mode == "file")
    app.step_layer(1); app.update()
    check("Nodes + down -> Blocks", app.view_mode == "node")
    app.step_layer(1); app.update()
    check("Blocks + down stays (clamped)", app.view_mode == "node")
    app.step_layer(-1); app.update()
    check("Blocks + up -> Nodes", app.view_mode == "file")
    app.step_layer(-1); app.step_layer(-1); app.update()
    check("Files + up stays (clamped)", app.view_mode == "files")

    # real key events through the bound handler
    app.focus_force(); app.update()
    app.focus_set(); app.update()
    app.event_generate("<Key-Down>"); app.update()
    check("Down key event steps to Nodes", app.view_mode == "file")
    app.event_generate("<Key-Up>"); app.update()
    check("Up key event steps back to Files", app.view_mode == "files")

    # bare key pauses while a text widget has focus
    e = tk.Entry(app); e.pack(); app.update(); e.focus_force(); app.update()
    app.event_generate("<Key-Down>"); app.update()
    check("Down ignored while an Entry has focus", app.view_mode == "files")
    e.destroy(); app.focus_set(); app.update()

    # rebinding
    app.settings["keybinds"] = {"layer_down": "Control-Key-j", "layer_up": "Control-Key-k"}
    app.apply_keybinds(); app.update()
    app.event_generate("<Key-Down>"); app.update()
    check("old Down no longer bound after rebind", app.view_mode == "files")
    app.event_generate("<Control-Key-j>"); app.update()
    check("Ctrl+J steps down", app.view_mode == "file")
    app.event_generate("<Control-Key-k>"); app.update()
    check("Ctrl+K steps up", app.view_mode == "files")
    # existing jump keys keep working
    app.event_generate("<Control-Key-3>"); app.update()
    check("Ctrl+3 still jumps to Blocks", app.view_mode == "node")

    check("get_keybinds fills missing step keys", app.get_keybinds()["layer_up"] == "Control-Key-k")
    app.settings["keybinds"] = {}
    check("empty saved keybinds -> defaults", app.get_keybinds()["layer_down"] == "Key-Down")
    # ---------- settings dialog capture ----------
    app.settings["keybinds"] = {}
    app.apply_keybinds(); saved.clear()
    app.settings_dialog(); app.update(); app.update()
    dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
    def walk(w):
        for c in w.winfo_children():
            yield c; yield from walk(c)
    btns = [w for w in walk(dlg) if isinstance(w, tk.Button)]
    by_text = {str(b.cget("text")): b for b in btns}
    check("dialog lists Up and Down rows", "Up" in by_text and "Down" in by_text)
    save_btn = [b for b in btns if "Save" in str(b.cget("text"))][0]
    dlg.update_idletasks()
    check("Save button fully visible in dialog", save_btn.winfo_rooty() + save_btn.winfo_height() <= dlg.winfo_rooty() + dlg.winfo_height())

    def press(btn, keysym, state=0):
        btn.invoke(); dlg.update()
        check("capture prompt shown", "Press keys" in str(btn.cget("text")))
        btn.event_generate("<KeyPress>", keysym=keysym, state=state); dlg.update()

    up_btn = by_text["Up"]
    press(up_btn, "Prior")
    check("capture shows new key + saved instantly", str(up_btn.cget("text")) == "Prior" and saved and saved[-1]["layer_up"] == "Key-Prior")
    check("capture applied live (PageUp now bound)", "<Key-Prior>" in app._layer_key_seqs and "<Key-Up>" not in app._layer_key_seqs)

    n = len(saved)
    import ui_palette
    warned = []
    ui_palette.messagebox.showwarning = lambda *a, **k: warned.append(a)
    press(by_text["Down"], "Prior")  # same key as Up now -> rejected
    check("duplicate shows a warning and restores the label", len(warned) == 1 and str(by_text["Down"].cget("text")) == "Down")
    check("duplicate not saved", len(saved) == n and app.get_keybinds()["layer_down"] == "Key-Down")

    # Escape cancels, plain letter waits
    b = by_text["Ctrl+1"]
    b.invoke(); dlg.update()
    b.event_generate("<KeyPress>", keysym="a"); dlg.update()
    check("plain letter keeps waiting", "Press keys" in str(b.cget("text")))
    b.event_generate("<KeyPress>", keysym="Escape"); dlg.update()
    check("Escape restores label, no save", str(b.cget("text")) == "Ctrl+1" and len(saved) == n)
    dlg.destroy(); app.update()

    app.destroy()
    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)

main()
