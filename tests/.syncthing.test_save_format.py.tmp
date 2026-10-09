"""Save format setting: sidecar (default) vs embedded node data, strict sidecar
parsing, rebuild when the sidecar is missing/stale/damaged, splitting a file
with no markers by top-level class/def. Run under Xvfb."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable as P
import ui_codegen, ui_import
from ui import BlocklinerUI
from ui_common import DEFAULT_SETTINGS, normalize_save_format
from nodes_model import make_node, function_nodes_in_tree_order

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def pure():
    check("factory default is sidecar", DEFAULT_SETTINGS["save_format"] == "sidecar")
    check("garbage setting falls back to sidecar", normalize_save_format("zzz") == "sidecar" and normalize_save_format(None) == "sidecar")
    check("embedded is kept", normalize_save_format("embedded") == "embedded")
    check("sidecar path", P.sidecar_path("/a/b.py") == "/a/b.py.blockliner.json")
    meta = {"v": 1, "language": "python", "nodes": {"a": {"name": "A", "kind": "function"}}}
    m, d = P.parse_sidecar(P.render_sidecar(meta))
    check("sidecar round trip", m == meta and d == [])
    for label, bad in (("invalid json", "{nope"), ("list", "[1]"), ("no nodes", "{}"), ("entry not object", '{"nodes":{"a":3}}')):
        m, d = P.parse_sidecar(bad)
        check(f"sidecar rejected: {label}", m is None and len(d) == 1 and "ignored" in d[0])
    src = "import os\nX = 1\n\n@dec\ndef a():\n    return 1\n\nclass B:\n    def m(self):\n        pass\n\nprint(a())\n"
    chunks = P.split_python_top_level(src)
    check("split names/order", [n for n, _ in chunks] == ["top_level", "a", "B", "top_level"])
    check("split keeps decorator with its def", chunks[1][1].lstrip().startswith("@dec"))
    check("split is lossless", "".join(c for _, c in chunks) == src)
    check("wrap+strip is lossless", P.strip_portable(P.wrap_with_markers(chunks)) == src)
    wrapped = P.wrap_with_markers([("f", "x\n"), ("f", "y\n"), ("bad name!", "z\n")])
    ids = [n["id"] for n in P.parse_portable(wrapped)[0]]
    check("ids unique and safe", ids == ["f", "f_2", "bad_name_"])
    tail_src = "def f():\n    pass\n\n# trailing comment\n"
    check("trailing comment after the last def is kept", "".join(c for _, c in P.split_python_top_level(tail_src)) == tail_src)
    check("syntax error -> None", P.split_python_top_level("def (:\n") is None)
    check("empty file -> no chunks", P.split_python_top_level("") == [])

def main():
    pure()
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    for mod in (ui_codegen, ui_import):
        mod.messagebox.showinfo = lambda *a, **k: None
        mod.messagebox.showerror = lambda *a, **k: None
        mod.messagebox.showwarning = lambda *a, **k: None
    app.maybe_notify = lambda *a, **k: None

    tab = app.tabs[app.active_tab_index]
    fn = function_nodes_in_tree_order(tab["nodes"])
    bid = app.get_raw_code_block_id("python"); pname = app.get_raw_code_param_name(bid)
    fn[0]["blocks"] = [(bid, {pname: "one = 1"})]
    extra = make_node("second", node_id="ab12cd34", blocks=[(bid, {pname: "two = 2"})], order=2)
    extra["canvas_x"], extra["canvas_y"] = 555, 77
    tab["nodes"].append(extra)
    tab["active_node_id"] = fn[0]["id"]; app.project_blocks = fn[0]["blocks"]

    # panel text by setting
    app.settings["save_format"] = "sidecar"; app.update_generated_code()
    panel = app.code_text.get(1.0, "end")
    check("sidecar mode: panel has markers", "$$$blockliner:node:ab12cd34$$$ start" in panel)
    check("sidecar mode: panel has NO metadata block", P.META_START_TAG not in panel)
    app.settings["save_format"] = "embedded"; app.update_generated_code()
    check("embedded mode: panel has metadata block", P.META_START_TAG in app.code_text.get(1.0, "end"))
    app.settings["save_format"] = "bogus"; app.update_generated_code()
    check("garbage setting behaves like sidecar", P.META_START_TAG not in app.code_text.get(1.0, "end"))

    tmp = tempfile.mkdtemp()
    def export(setting, name):
        app.settings["save_format"] = setting; app.update_generated_code()
        path = os.path.join(tmp, name)
        ui_codegen.filedialog.asksaveasfilename = lambda **k: path
        app.export_code()
        return path

    p1 = export("sidecar", "s.py")
    side = P.sidecar_path(p1)
    check("sidecar export writes the code file without metadata", os.path.exists(p1) and P.META_START_TAG not in open(p1).read())
    check("sidecar export writes the sidecar", os.path.exists(side))
    sm = json.load(open(side))
    check("sidecar holds node names + position", sm["nodes"]["ab12cd34"]["name"] == "second" and sm["nodes"]["ab12cd34"]["x"] == 555)
    p2 = export("embedded", "e.py")
    check("embedded export: metadata inside, no sidecar", P.META_START_TAG in open(p2).read() and not os.path.exists(P.sidecar_path(p2)))

    def reopen(code, sidecar_text, title):
        ui_import_picked = None
        notes = app.load_portable_text(code, title=title, sidecar_text=sidecar_text)
        return notes, app.tabs[app.active_tab_index]
    code = open(p1).read()
    notes, t = reopen(code, open(side).read(), "with_sidecar")
    names = {n["name"] for n in function_nodes_in_tree_order(t["nodes"])}
    second = next(n for n in function_nodes_in_tree_order(t["nodes"]) if n["id"] == "ab12cd34")
    check("sidecar restores names and position", "second" in names and (second["canvas_x"], second["canvas_y"]) == (555, 77) and not notes)
    other = json.loads(open(side).read()); other["language"] = "c"
    notes, t = reopen(code, json.dumps(other), "sidecar_lang")
    check("sidecar decides the language of the new tab", t["language"] == "c")
    app.current_language = "python"; app.lang_var.set("python")
    notes, t = reopen(code, None, "no_sidecar")
    second = next(n for n in function_nodes_in_tree_order(t["nodes"]) if n["id"] == "ab12cd34")
    check("missing sidecar: rebuilt from markers (id as name)", second["name"] == "ab12cd34" and len(function_nodes_in_tree_order(t["nodes"])) == 2)
    notes, t = reopen(code, "{broken", "bad_sidecar")
    check("damaged sidecar: still opens, says why", len(function_nodes_in_tree_order(t["nodes"])) == 2 and any("sidecar" in n for n in notes))
    stale = json.loads(open(side).read()); del stale["nodes"]["ab12cd34"]
    notes, t = reopen(code, json.dumps(stale), "stale_sidecar")
    check("stale sidecar: marker node kept, noted", len(function_nodes_in_tree_order(t["nodes"])) == 2 and any("not in the metadata" in n for n in notes))
    notes, t = reopen(p2 and open(p2).read(), open(side).read(), "embedded_wins")
    check("block inside the file wins over a sidecar", not any("sidecar" in n for n in notes))

    # file with no markers
    plain = "import os\n\ndef load():\n    return 1\n\nclass Player:\n    pass\n"
    path = os.path.join(tmp, "plain.py"); open(path, "w").write(plain)
    asked = []
    ui_import.messagebox.askyesno = lambda *a, **k: (asked.append(a[0]) or True)
    class D:
        destroyed = False
        def destroy(self): self.destroyed = True
    d = D(); app.current_language = "python"
    n_tabs = len(app.tabs)
    check("unmarked python: offer made and accepted", app._offer_split_unmarked(plain, d) is True and asked and d.destroyed)
    t = app.tabs[app.active_tab_index]
    check("unmarked python: one node per top-level item", [n["name"] for n in function_nodes_in_tree_order(t["nodes"])] == ["top_level", "load", "Player"] and len(app.tabs) == n_tabs + 1)
    reg = P.strip_portable(app.generate_portable_for_tab(t, "python", embed_meta=False))
    squash = lambda x: "".join(x.split())
    check("unmarked python: every original statement is still in the generated code", all(squash(l) in squash(reg) for l in plain.splitlines() if l.strip()))
    ui_import.messagebox.askyesno = lambda *a, **k: False
    n_tabs = len(app.tabs); d = D()
    check("declined offer changes nothing", app._offer_split_unmarked(plain, d) is False and not d.destroyed and len(app.tabs) == n_tabs)
    asked.clear(); ui_import.messagebox.askyesno = lambda *a, **k: (asked.append(a[0]) or False)
    check("marked file is never offered a split", app._offer_split_unmarked(code, D()) is False and not asked)
    check("single-chunk file is not offered", app._offer_split_unmarked("x = 1\n", D()) is False and not asked)
    app.current_language = "go"
    check("non-python file is not offered", app._offer_split_unmarked(plain, D()) is False and not asked)

    app.destroy()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
