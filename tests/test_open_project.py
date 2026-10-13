"""Open project: language-independent top-level split + folder scan + import dialog. Headless (Xvfb)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from tkinter import messagebox
import portable, project_scan
from ui_common import LANGUAGE_EXTENSIONS
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)
def names(text): return [n for n, _ in portable.split_top_level(text)]
def lossless(text): return "".join(c for _, c in portable.split_top_level(text)) == text
def widgets(w, cls):
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, cls): out.append(ch)
        out += widgets(ch, cls)
    return out

PY = "import os\nimport sys\n\nclass A(B):\n    def f(self):\n        pass\n\n    x = 1\n\nA.go()\nprint(1)\n\n@dec\ndef g():\n    return 1\n\nif __name__ == '__main__':\n    g()\n"
C = "#include <stdio.h>\n#include <x.h>\n\nint main(int argc)\n{\n    return 0;\n}\n\nstatic int add(int a)\n{\n  return a;\n}\n"
RS = "use std::io;\n\n// doc\n#[derive(Debug)]\nstruct P {\n    x: i32,\n}\n\nimpl P {\n    fn new() -> P { P{x:1} }\n}\n\nfn main() {\n    println!(\"a\");\n}\n"
GO = "package main\n\nimport \"fmt\"\n\nfunc (s *S) Run() {\n\tfmt.Println()\n}\n\nfunc main() {\n}\n"
HTML = "<!DOCTYPE html>\n<html>\n  <body>\n  </body>\n</html>\n"

def main():
    # ---- the rule, on several languages
    check("python: top-level code runs are one node, class/def/if are nodes",
          names(PY) == ["top_level", "A", "top_level", "g", "if"])
    check("python: decorator stays with its def", portable.split_top_level(PY)[3][1].startswith("@dec\n"))
    check("python: class body (methods, blank lines) stays in one node", "def f(self)" in portable.split_top_level(PY)[1][1] and "x = 1" in portable.split_top_level(PY)[1][1])
    check("C: #includes are one node, Allman functions keep their braces", names(C) == ["top_level", "main", "add"])
    check("Rust: use / struct / impl / fn, attributes+doc attach", names(RS) == ["top_level", "P", "P", "main"]
          and portable.split_top_level(RS)[1][1].startswith("// doc\n#[derive(Debug)]\n"))
    check("Go: method name from receiver form", names(GO) == ["top_level", "Run", "main"])
    check("HTML: closing tag stays with the element", names(HTML) == ["top_level", "html"])
    check("C#-style namespace is one node", names("namespace App\n{\n    class A\n    {\n    }\n}\n") == ["App"])
    check("nothing is ever dropped", all(lossless(t) for t in (PY, C, RS, GO, HTML, "", "x", "a\nb\n", "\n\n", "    indented only\n", '"""d\nnot head\n"""\nx=1\n')))
    check("empty text -> no chunks", portable.split_top_level("") == [])
    check("plain lines only -> one top_level node", portable.split_top_level("a\nb\nc\n") == [("top_level", "a\nb\nc\n")])
    check("lines inside a triple-quoted string are not headers", names('"""d\nfoo\n    bar\n"""\nx=1\n') == ["top_level"])
    check("leading indented line does not crash", lossless("  x\ny\n"))

    # ---- folder scan
    root = tempfile.mkdtemp()
    def w(rel, data, mode="w"):
        p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode) as f: f.write(data)
    w("main.py", PY); w("src/lib.rs", RS); w("src/util.c", C); w("README.md", "# hi\n")
    w("node_modules/x/index.js", "var a=1;\n"); w(".git/config", "x"); w("data.py", b"\0\1\2", "wb")
    w("big.py", "x=1\n" * 300000); w("notes.go", GO)
    entries, trunc = project_scan.scan_folder(root, LANGUAGE_EXTENSIONS)
    rels = [e["rel"] for e in entries]
    check("skips node_modules and .git", not [r for r in rels if r.startswith(("node_modules", ".git"))])
    check("sorted relative paths with forward slashes", rels == sorted(rels, key=str.lower) and "src/lib.rs" in rels)
    by = {e["rel"]: e for e in entries}
    check("known types are ok with their language", by["main.py"]["ok"] and by["main.py"]["language"] == "python" and by["src/lib.rs"]["language"] == "rust")
    check("unknown type listed but not importable", not by["README.md"]["ok"] and by["README.md"]["reason"])
    check("binary file refused", not by["data.py"]["ok"] and "text" in by["data.py"]["reason"])
    check("too-big file refused", not by["big.py"]["ok"] and "big" in by["big.py"]["reason"])
    e2, t2 = project_scan.scan_folder(root, LANGUAGE_EXTENSIONS, max_files=2)
    check("max_files truncates and says so", len(e2) == 2 and t2)
    check("missing folder never raises", project_scan.scan_folder(os.path.join(root, "nope"), LANGUAGE_EXTENSIONS) == ([], False))

    # ---- UI import
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1300x800"); app.update()
    answers, tokens = [], []
    _wrap = portable.wrap_with_markers
    portable.wrap_with_markers = lambda chunks, token="#": (tokens.append(token), _wrap(chunks, token))[1]
    messagebox.askyesno = lambda *a, **k: answers.append(a[0]) or True
    check("File menu has Open Project", any(l == "Open Project..." for t, es in app.topbar_menu_spec() for l, _ in [e for e in es if e]))
    n0 = len(app.tabs)
    dlg = app.open_project_dialog(folder=root); app.update()
    btns = [b for b in widgets(dlg, tk.Button)]
    arrows = [b for b in btns if b.cget("text") == "↑"]
    check("one arrow button per file", len(arrows) == len(entries))
    check("arrows disabled for unsupported files", sum(1 for b in arrows if str(b.cget("state")) == "disabled") == 3)
    check("import-all shows the count", any(b.cget("text") == f"↑ Import all ({sum(e['ok'] for e in entries)})" for b in btns))

    row = dict(zip([e["rel"] for e in entries], arrows))
    row["main.py"].invoke(); app.update(); app.update()
    check("asked once whether to split", answers == ["Split into nodes?"])
    check("one file tab added", len(app.tabs) == n0 + 1)
    tab = app.tabs[-1]
    check("tab named after the file, python", tab["title"] == "main.py" and tab["language"] == "python")
    top_names = [n["name"] for n in tab["nodes"]]
    print("   node names:", top_names)
    check("split into nodes by top-level code (unique names)", len(top_names) == 5 and len(set(top_names)) == 5 and top_names[1] == "A" and top_names[3] == "g")
    check("imported arrow turns into a tick", row["main.py"].cget("text") == "✓")
    code = app.generate_code_for_tab(tab, "python")
    check("original code survives the round trip", "class A(B):" in code and "def g():" in code and "print(1)" in code and "import sys" in code)

    row["src/lib.rs"].invoke(); app.update(); app.update()
    check("answer remembered (not asked again)", answers == ["Split into nodes?"])
    rs = app.tabs[-1]
    rs = app.tabs[-1]
    print("   rust tab:", rs["language"], rs["title"], [n["name"] for n in rs["nodes"]])
    check("other language gets its own language pack", rs["language"] == "rust" and rs["title"] == "lib.rs")
    check("rust split by the same rule", [n["name"] for n in rs["nodes"]] == ["top_level", "P", "P_2", "main"])
    check("rust code survives", "struct P" in app.generate_code_for_tab(rs, "rust"))

    check("markers use each language's comment token", tokens[:2] == ["#", "//"])
    nt = len(app.tabs)
    dlg._import_all_btn.invoke(); app.update(); app.update()
    check("import all opens only what is left", len(app.tabs) == nt + 2)
    check("ends on the Files layer", app.view_mode == "files")
    dlg._import_all_btn.invoke(); app.update()
    check("nothing is imported twice", len(app.tabs) == nt + 2)
    dlg.destroy()

    # no-split answer = one node per file
    messagebox.askyesno = lambda *a, **k: False
    dlg2 = app.open_project_dialog(folder=root); app.update()
    arr2 = dict(zip([e["rel"] for e in entries], [b for b in widgets(dlg2, tk.Button) if b.cget("text") == "↑"]))
    arr2["main.py"].invoke(); app.update(); app.update()
    one = app.tabs[-1]
    check("No = one node for the whole file", len(one["nodes"]) == 1 and one["nodes"][0]["name"] == "main")
    dlg2.destroy()

    # unsupported / missing language never crash
    check("unsupported entry imports nothing", app.import_project_file(by["README.md"], True) is None)
    check("cancelled folder dialog does nothing", (setattr(app, "x", 0) or True) and app.open_project_dialog(folder="") is None)
    app.destroy()
    print("\nFAILURES:", FAILURES if FAILURES else "none")
    sys.exit(1 if FAILURES else 0)

main()
