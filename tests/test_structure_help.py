"""Pure + window check of the "How is a project built?" explainer."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import structure_help as SH

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def pure():
    check("three levels, big to small: file, node, block", [l["key"] for l in SH.LEVELS] == ["file", "node", "block"])
    check("each level points at its own layer", [l["layer"] for l in SH.LEVELS] == ["files", "nodes", "blocks"])
    out = []
    code = SH.example_code()
    env = {"input": lambda _p="": "20", "print": lambda *a: out.append(" ".join(map(str, a)))}
    exec(compile(code, "<example>", "exec"), env)
    check("the example is a real program that runs", out == ["allow entry", "bye"])
    rows = SH.code_rows()
    check("every node has a start and an end marker row", all(sum(1 for n, t in rows if n == name and "$$$" in t) == 2 for name, _ in SH.EXAMPLE))
    check("the rows contain every line of the program", [t for _n, t in rows if "$$$" not in t] == code.rstrip("\n").split("\n"))

def window():
    try:
        from ui import BlocklinerUI
    except ImportError:
        return
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1400x900+0+0")
    try:
        for _ in range(4): app.update()
        check("the layer bar has a How it fits button", app.structure_btn.winfo_ismapped())
        app.structure_btn.invoke()
        win = app.__dict__.get("_structure_win")
        for _ in range(4): app.update()
        check("the button opens the window", win is not None and win.winfo_exists())
        texts = []
        def walk(w):
            for c in w.winfo_children():
                try: texts.append(c.cget("text"))
                except Exception: pass
                walk(c)
        walk(win)
        joined = "\n".join(texts)
        check("it shows a file, nodes and blocks", "entry.py" in joined and "check_age" in joined and 'print("allow entry")' in joined)
        check("pressing the button again reuses the window", app.show_structure_help() is win)
        goto = [b for b in [c for c in _buttons(win)] if "Nodes layer" in b.cget("text")]
        check("a Show me button exists per level", len([b for b in _buttons(win) if b.cget("text").startswith("Show me")]) == 3)
        goto[0].invoke()
        for _ in range(4): app.update()
        check("Show me goes to that layer and closes the window", app.view_mode == "file" and not win.winfo_exists())
        check("Help lists it and the palette can find it", app.command_registry.get("help.structure") is not None)
    finally:
        app.destroy()

def _buttons(w):
    out = []
    for c in w.winfo_children():
        if c.winfo_class() == "Button": out.append(c)
        out.extend(_buttons(c))
    return out

if __name__ == "__main__":
    pure()
    window()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)
