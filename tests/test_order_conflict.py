"""Setting 'order_conflict' (take / swap / ask) for the node-order dialog and
its Settings row. Run under Xvfb like the other tests."""
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui, ui_palette
from ui import BlocklinerUI, make_node, normalize_orders
from ui_common import DEFAULT_SETTINGS, ORDER_CONFLICT_CHOICES

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def walk(w):
    for c in w.winfo_children():
        yield c; yield from walk(c)

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0"); app.update()
    saved = []
    app.save_app_settings = lambda: saved.append(app.settings.get("order_conflict"))
    tab = app.tabs[0]
    asked = []; warned = []
    ui.messagebox.showwarning = lambda t, m, **k: warned.append(m)
    def answer(v): ui.messagebox.askyesnocancel = lambda t, m, **k: (asked.append(m), v)[1]
    def setup():
        a = make_node("A", node_id="a"); b = make_node("B", node_id="b"); c = make_node("C", node_id="c")
        tab["nodes"] = [a, b, c]; tab["active_node_id"] = "a"; tab["file_view_path"] = []
        normalize_orders(tab["nodes"]); asked.clear(); warned.clear()
        return a, b, c   # orders 1,2,3 (a is entry point? a may be unlocked here)
    def ask_number(n): ui.simpledialog.askstring = lambda *a, **k: str(n)
    def orders(*ns): return [n.get("order") for n in ns]

    check("factory default is 'take'", DEFAULT_SETTINGS["order_conflict"] == "take")
    check("three choices offered", [k for k, _ in ORDER_CONFLICT_CHOICES] == ["take", "swap", "ask"])

    # take (default / missing key / garbage value) -> no popup, other node unassigned
    for label, setting in (("take", "take"), ("missing key", None), ("garbage value", "bogus")):
        app.settings.pop("order_conflict", None)
        if setting: app.settings["order_conflict"] = setting
        a, b, c = setup(); b["locked"] = False; c["locked"] = False
        ask_number(3); app.set_node_order_dialog("b")
        if setting == "bogus":
            check("garbage value behaves like take (not ask)", not asked and orders(b, c) == [3, None])
        else:
            check(f"{label}: no popup, B=3, C unassigned", not asked and orders(b, c) == [3, None])

    # swap -> no popup, other node gets my old number
    app.settings["order_conflict"] = "swap"
    a, b, c = setup(); ask_number(3); app.set_node_order_dialog("b")
    check("swap: no popup, B=3 and C=2", not asked and orders(b, c) == [3, 2])

    # ask -> popup; yes=swap, no=take, cancel=nothing
    app.settings["order_conflict"] = "ask"
    for ans, want, label in ((True, [3, 2], "yes = swap"), (False, [3, None], "no = take"), (None, [2, 3], "cancel = unchanged")):
        a, b, c = setup(); answer(ans); ask_number(3); app.set_node_order_dialog("b")
        check(f"ask: popup shown, {label}", len(asked) == 1 and orders(b, c) == want)

    # no collision -> never asks or changes others, in every mode
    for mode in ("take", "swap", "ask"):
        app.settings["order_conflict"] = mode
        a, b, c = setup(); ask_number(9); app.set_node_order_dialog("b")
        check(f"{mode}: free number just applies, no popup", not asked and orders(a, b, c) == [1, 9, 3])

    # locked node's number can never be taken, whatever the setting
    app.settings["order_conflict"] = "take"
    a, b, c = setup(); a["locked"] = True; a["order"] = 1; ask_number(1); app.set_node_order_dialog("c")
    check("locked holder: warning, nothing changes, no popup", len(warned) == 1 and not asked and orders(a, c) == [1, 3])

    # ---- Settings dialog row ----
    def open_dialog():
        app.settings_dialog(); app.update(); app.update()
        dlg = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
        combos = [w for w in walk(dlg) if isinstance(w, ui_palette.ttk.Combobox) and "Ask me" in str(w.cget("values"))]
        save = [w for w in walk(dlg) if isinstance(w, tk.Button) and "Save" in str(w.cget("text"))][0]
        return dlg, combos, save
    app.settings["order_conflict"] = "swap"
    dlg, combos, save = open_dialog()
    check("dialog has exactly one order-conflict row", len(combos) == 1)
    check("row shows the saved choice (swap)", combos[0].get().startswith("Swap"))
    dlg.update_idletasks()
    check("Save button fully visible and not squeezed", save.winfo_height() > 20 and save.winfo_rooty() + save.winfo_height() <= dlg.winfo_rooty() + dlg.winfo_height())
    check("dialog fits on screen", dlg.winfo_rooty() >= 0 and dlg.winfo_rooty() + dlg.winfo_height() <= dlg.winfo_screenheight())
    combos[0].set(ORDER_CONFLICT_CHOICES[2][1]); save.invoke(); app.update()
    check("choosing 'Ask me' + Save persists 'ask'", app.settings["order_conflict"] == "ask" and saved[-1] == "ask")
    dlg, combos, save = open_dialog()
    check("reopened dialog shows 'Ask me'", combos[0].get().startswith("Ask"))
    combos[0].set(ORDER_CONFLICT_CHOICES[0][1]); dlg.event_generate("<Escape>"); app.update()
    check("Cancel/Esc does not change it", app.settings["order_conflict"] == "ask")
    # small screen: dialog is capped, but Save must stay visible and unsqueezed
    dlg.destroy(); app.update()
    real_sh = tk.Toplevel.winfo_screenheight
    tk.Toplevel.winfo_screenheight = lambda self: 600
    try:
        dlg, combos, save = open_dialog(); dlg.update_idletasks()
        check("small screen: dialog capped to screen height - 80", dlg.winfo_height() == 520)
        cv = [w for w in walk(dlg) if isinstance(w, tk.Canvas)][0]
        sb = [w for w in walk(dlg) if isinstance(w, ui_palette.ttk.Scrollbar)][0]
        check("small screen: body scrolls (scrollbar shown, content taller than view)", sb.winfo_ismapped() and cv.yview()[1] < 1.0)
        down_btn = [w for w in walk(dlg) if isinstance(w, tk.Button) and w.cget("text") == "Down"][0]
        cv.yview_moveto(1.0); dlg.update()
        check("small screen: last keybind row reachable by scrolling", down_btn.winfo_rooty() + down_btn.winfo_height() <= cv.winfo_rooty() + cv.winfo_height() + 2 and down_btn.winfo_rooty() >= cv.winfo_rooty())
        cv.yview_moveto(0.0); dlg.update()
        dlg.event_generate("<Button-5>"); dlg.update()
        check("small screen: mouse wheel over the dialog scrolls the body", cv.yview()[0] > 0.0)
        pos = cv.yview()[0]; dlg.event_generate("<Button-4>"); dlg.update()
        check("small screen: wheel up scrolls back up", cv.yview()[0] < pos)
        pos = cv.yview()[0]; dlg.event_generate("<MouseWheel>", delta=-120); dlg.update()
        check("small screen: Windows-style wheel (delta<0) scrolls down", cv.yview()[0] > pos or cv.yview()[1] >= 1.0)
        check("small screen: Save still visible and not squeezed", save.winfo_height() > 20 and save.winfo_rooty() + save.winfo_height() <= dlg.winfo_rooty() + dlg.winfo_height())
        dlg.destroy(); app.update()
    finally:
        tk.Toplevel.winfo_screenheight = real_sh
    dlg.destroy(); app.update()
    app.settings["order_conflict"] = "garbage"
    dlg, combos, save = open_dialog()
    check("garbage saved value shows as 'take' row", combos[0].get().startswith("Take"))
    save.invoke(); app.update()
    check("saving repairs garbage to 'take'", app.settings["order_conflict"] == "take")

    app.destroy()
    print("\nFAILED:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
