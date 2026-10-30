"""Popup windows and the 'open window' button (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_pack, ui_node, ui_parse
from ui_tree import UITree

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui_packs")
    pack = ui_pack.find_packs([root], "python")[0][0]
    check("popup is a root type, never in the palette", "popup" in pack.root_types
          and all(w["type"] != "popup" for _c, ws in pack.palette() for w in ws))
    pop_tree = UITree.new(pack.id, root_type="popup", root_name="top", props=pack.defaults("popup"), is_container=pack.is_container)
    pop = ui_node.make_ui_node("settings", "p1", pop_tree)
    text, problems = ui_node.generate_text(pop, pack)
    check("popup builds a Toplevel", "top = tk.Toplevel()" in text and not problems)
    check("popup has no call or mainloop of its own", "build_settings()" not in text.split("def build_settings")[1].split("return")[1]
          and "mainloop" not in text)
    prev, _ = ui_node.preview_source(pop, pack)
    check("preview still opens and runs it", "ui = build_settings()" in prev and "mainloop()" in prev)
    check("a popup reads back from its code", ui_parse.read_back(pop, pack, text.strip())[0] is not None)

    main_tree = UITree.new(pack.id, root_type="window", root_name="root", props=pack.defaults("window"), is_container=pack.is_container)
    main_tree.add(main_tree.root["id"], "button", name="btn_settings", props={"text": "Settings"}, design={"w": 100, "h": 32})
    btn = next(n for n in main_tree.walk() if n["name"] == "btn_settings")
    main_tree.set_layout(btn["id"], manager="grid", row=0, column=0)
    main_tree.set_event(btn["id"], "command", "p1")
    mainn = ui_node.make_ui_node("main", "m1", main_tree)
    resolve = lambda i: ui_node.function_name(pop) if i == "p1" else None
    mtext, mprob = ui_node.generate_text(mainn, pack, resolve)
    check("button opens the popup by calling its builder", "btn_settings.configure(command=build_settings)" in mtext and not mprob)
    check("main window still runs", "ui.root.mainloop()" in mtext)
    tree, probs = ui_parse.read_back(mainn, pack, mtext.strip(), resolve, {"build_settings": "p1"}.get)
    check("the open-window link reads back", tree is not None and next(n for n in tree.walk() if n["name"] == "btn_settings")["events"].get("command") == "p1")
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
