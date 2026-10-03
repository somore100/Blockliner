"""Portable markers in the UI: preview shows them, Run/clean text doesn't,
strip == old output in all 9 languages, round trip through
load_portable_text, Code -> Blocks ignores markers. Run under Xvfb."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable as P
from ui import BlocklinerUI
from nodes_model import make_node, sorted_function_nodes, function_nodes_in_tree_order

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

LANGS = ["python", "c", "cpp", "csharp", "java", "javascript", "rust", "go", "html"]

def fresh_tab(app, lang):
    app.sync_active_tab_state()
    app.current_language = lang
    app.lang_var.set(lang)
    app.load_blocks_for_language(lang, verbose=False)
    app.load_and_merge_custom_blocks()
    nodes = app.build_initial_nodes_for_language(lang)
    app.tabs.append({"title": f"t_{lang}", "language": lang, "nodes": nodes,
                     "active_node_id": None, "filepath": None, "dirty": False})
    app.active_tab_index = len(app.tabs) - 1
    tab = app.tabs[-1]
    fn = function_nodes_in_tree_order(nodes)
    return tab, fn

def raw(app, lang, line):
    bid = app.get_raw_code_block_id(lang)
    return (bid, {app.get_raw_code_param_name(bid): line})

def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1200x800+0+0"); app.update()
    for lang in LANGS:
        tab, fn = fresh_tab(app, lang)
        first = fn[0]
        first["blocks"] = [raw(app, lang, "one"), raw(app, lang, "two")]
        extra = make_node("second", node_id="ab12cd34", blocks=[raw(app, lang, "three")], order=2)
        extra["canvas_x"], extra["canvas_y"] = 555, 77
        # put it next to the entry node at the same level
        parent_level = tab["nodes"] if first in tab["nodes"] else next(n for n in tab["nodes"] if first in n["child_nodes"])["child_nodes"]
        parent_level.append(extra)
        tab["active_node_id"] = first["id"]
        app.project_blocks = first["blocks"]
        app.update_generated_code()

        clean = app.generate_code_for_tab(tab, lang)
        port = app.generate_portable_for_tab(tab, lang)
        check(f"{lang}: portable has node markers + metadata", port.count("$$$blockliner:node:") == 2 * len(fn) + 2 and "$$$blockliner:meta:end$$$" in port)
        check(f"{lang}: strip(portable) == old generated code", P.strip_portable(port) == clean)
        shown = app.code_text.get("1.0", "end-1c")
        check(f"{lang}: preview panel shows the portable text", shown == port)
        check(f"{lang}: Run/clean text has no markers or metadata", "blockliner" not in app.get_clean_code() and app.get_clean_code() == clean.strip())

        # round trip into a new tab
        before = len(app.tabs)
        notes = app.load_portable_text(port, title=f"rt_{lang}")
        new_tab = app.tabs[app.active_tab_index]
        check(f"{lang}: opened as a new tab", len(app.tabs) == before + 1 and new_tab["title"] == f"rt_{lang}" and app.current_language == lang)
        check(f"{lang}: no diagnostics on a clean round trip", notes == [])
        check(f"{lang}: regenerated code identical", app.generate_code_for_tab(new_tab, lang) == clean)
        ids_before = [n["id"] for n in sorted_function_nodes(tab["nodes"])]
        ids_after = [n["id"] for n in sorted_function_nodes(new_tab["nodes"])]
        check(f"{lang}: node ids and run order preserved", ids_before == ids_after)
        got = {n["id"]: n for n in function_nodes_in_tree_order(new_tab["nodes"])}
        check(f"{lang}: saved position + name restored", (got["ab12cd34"]["canvas_x"], got["ab12cd34"]["canvas_y"], got["ab12cd34"]["name"]) == (555, 77, "second"))
        check(f"{lang}: wrapper nodes restored", [n["kind"] for n in new_tab["nodes"]] == [n["kind"] for n in tab["nodes"]])
        check(f"{lang}: portable of the reopened tab equals the original", app.generate_portable_for_tab(new_tab, lang) == port)

    # no metadata: skeleton still opens and generates the same code
    tab, fn = fresh_tab(app, "python")
    fn[0]["blocks"] = [raw(app, "python", "alpha = 1")]
    tab["active_node_id"] = fn[0]["id"]; app.project_blocks = fn[0]["blocks"]
    port = app.generate_portable_for_tab(tab, "python")
    no_meta = port.split("\n\n# $$$blockliner:meta$$$")[0] + "\n"
    n_tabs = len(app.tabs)
    notes = app.load_portable_text(no_meta, title="skeleton")
    sk = app.tabs[app.active_tab_index]
    check("skeleton: opened and same code", len(app.tabs) == n_tabs + 1 and app.generate_code_for_tab(sk, "python").strip() == "alpha = 1")
    check("skeleton: flat nodes, no wires invented", all(not n["child_nodes"] and not n["references"] for n in sk["nodes"]))
    check("skeleton: not flagged as saved layout", "x" not in P.build_metadata(sk["nodes"], "python")["nodes"][sk["nodes"][0]["id"]])

    # damaged metadata is reported, nodes still open
    bad = port.replace('"v": 1', '"v": 1,,')
    notes = app.load_portable_text(bad, title="damaged")
    check("damaged metadata: reported and still opens", any("not valid JSON" in n for n in notes) and app.tabs[app.active_tab_index]["title"] == "damaged")

    # text without markers is not a portable file
    check("plain code is not treated as portable", app.load_portable_text("x = 1\n") is None)

    # Code -> Blocks ignores markers and never needs metadata
    tab, fn = fresh_tab(app, "python")
    app.switch_to_tab(app.active_tab_index) if False else None
    app.current_language = "python"
    blocks, matched, raw_count = app.import_code_to_blocks(P.strip_portable(port).strip())
    check("Code->Blocks: stripped text imports", matched + raw_count >= 1)
    import ui_import
    ui_import.messagebox.showerror = lambda *a, **k: None
    ui_import.messagebox.askyesno = lambda *a, **k: True
    ui_import.messagebox.showinfo = lambda *a, **k: None
    ui_import.messagebox.showwarning = lambda *a, **k: None
    app.project_blocks = []
    app.set_project_blocks([])
    app._convert_code_string_to_blocks(port)
    flat = [str(p) for _b, p in app.project_blocks]
    check("Code->Blocks: pasting the full portable text drops marker/metadata lines", app.project_blocks and not any("blockliner" in f for f in flat))

    app.destroy()
    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)

main()
