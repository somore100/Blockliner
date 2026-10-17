"""Right-click > Skip (purple, ComfyUI "bypass"): the node AND every call to it
stay in the generated code as ## comments (never run); Skip and Ignore exclude each other; saved with
the project. Headless (Xvfb)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import nodes_model as nm, portable, project_file
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def labels(menu): return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
def chip(name): return {"_nested_block": "func_call", "_nested_params": {"name": name, "args": ""}}

def ifs_i(lst):
    return next(i for i, b in enumerate(lst) if isinstance(b, tuple) and b[0] == "if_statement")

def main():
    # ---- pure: strip_skipped_calls
    names = {"gen_pw"}
    blocks = [("print_output", {"value": "'keep'"}),
              ("func_call", {"name": "gen_pw", "args": ""}),
              ("func_call", {"name": "other", "args": ""}),
              ("assign_variable", {"variable": "t", "value": chip("gen_pw")}),
              ("assign_variable", {"variable": "u", "value": chip("other")}),
              ("print_output", {"value": chip("gen_pw")}),
              ("if_statement", {"condition": "x", "_children": [("func_call", {"name": "gen_pw", "args": ""}),
                                                              ("print_output", {"value": "'in'"})]}),
              ("if_statement", {"condition": "y", "_children": [("func_call", {"name": "gen_pw", "args": ""})]}),
              None, ("x",)]
    import copy; snapshot = copy.deepcopy(blocks)
    out = nm.strip_skipped_calls(blocks, names)
    check("plain call to a skipped node is dropped", ("func_call", {"name": "gen_pw", "args": ""}) not in out)
    check("calls to other nodes stay", ("func_call", {"name": "other", "args": ""}) in out)
    check("assignment of a skipped call is dropped, others stay",
          not any(b and len(b) == 2 and b[0] == "assign_variable" and b[1]["variable"] == "t" for b in out if isinstance(b, tuple))
          and any(isinstance(b, tuple) and b[0] == "assign_variable" and b[1]["variable"] == "u" for b in out))
    check("a block holding a skipped call chip is dropped", not any(isinstance(b, tuple) and b[0] == "print_output" and isinstance(b[1]["value"], dict) for b in out))
    ifs = [b for b in out if isinstance(b, tuple) and b[0] == "if_statement"]
    check("calls inside containers are dropped too", ifs[0][1]["_children"] == [("print_output", {"value": "'in'"})])
    check("a container left empty stays (renders as pass)", ifs[1][1]["_children"] == [])
    check("the input list is never changed", blocks == snapshot)
    check("junk entries survive", None in out and ("x",) in out)
    rep = nm.strip_skipped_calls(blocks, names, replace=lambda e: ("raw_code", {"code": "## x"}))
    check("replace= swaps calls instead of dropping them", sum(1 for b_ in rep if b_ == ("raw_code", {"code": "## x"})) == 3
          and rep[ifs_i(rep)][1]["_children"][0] == ("raw_code", {"code": "## x"}))
    check("no skipped names = same list back", nm.strip_skipped_calls(blocks, set()) is blocks)
    a = make_node("a", node_id="a"); b = make_node("b", node_id="b"); b["skipped"] = True
    check("skipped_names", nm.skipped_names([a, b]) == {"b"})
    check("skipped node keeps its place in the run order", [n["id"] for n in nm.sorted_function_nodes([a, b])] == ["a", "b"])

    # ---- UI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    gen = make_node("gen_pw", node_id="gen_pw", blocks=[("assign_variable", {"variable": "text", "value": "'abc'"})])
    ui = make_node("ui", node_id="ui", blocks=[("print_output", {"value": "'hello'"}),
                                               ("assign_variable", {"variable": "t", "value": chip("gen_pw")}),
                                               ("func_call", {"name": "gen_pw", "args": ""})])
    ui2 = make_node("ui2", node_id="ui2", blocks=[("print_output", {"value": "'two'"})])
    nodes = [gen, ui, ui2]
    for i, n in enumerate(nodes): n["canvas_x"], n["canvas_y"] = 20 + i * 330, 20
    tab["nodes"] = nodes; tab["active_node_id"] = "ui"; tab["file_view_path"] = []
    app.project_blocks = ui["blocks"]; normalize_orders(nodes)
    app.switch_to_file_view(); app.update(); app.update()
    code = lambda: app.generate_code_for_tab(tab, "python")
    marked = lambda: app.generate_portable_for_tab(tab, "python", embed_meta=False)

    check("menu offers Skip", "Skip" in labels(app.build_node_menu("gen_pw")))
    check("code has the node and the calls before skipping", "text = 'abc'" in code() and "gen_pw()" in code())

    app.toggle_skip_node("gen_pw"); app.update()
    check("flag set", gen.get("skipped") is True)
    live = lambda c: [l for l in c.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    check("node code stays as a ## comment", "## text = 'abc'" in code())
    check("node code no longer runs", "text = 'abc'" not in live(code()) and not any("text = 'abc'" in l for l in live(code())))
    check("calls to it are ## comments", "## t = gen_pw()" in code() and "## gen_pw()" in code())
    check("no live call to it", not any("gen_pw" in l for l in live(code())))
    check("other code is untouched", "print('hello')" in live(code()) and "print('two')" in live(code()))
    check("the commented node sits in its run-order place", code().index("## text") < code().index("print('hello')"))
    ns = {}
    exec(compile(code(), "<gen>", "exec"), ns)
    check("generated program runs without the skipped node", "text" not in ns)
    check("marked (portable) output keeps the node's markers and comments",
          "$$$blockliner:node:gen_pw$$$" in marked() and "## text = 'abc'" in marked())
    check("the caller's own blocks are NOT edited", len(ui["blocks"]) == 3)
    check("the caller's own view still shows the call", "gen_pw()" in app.generate_code_for_node(ui, "python"))
    box = app._fileview_boxes["gen_pw"][1]
    check("box header turns purple", box.winfo_children()[0].cget("bg") == "#7b3fb0")
    check("menu now says Stop skipping", "Stop skipping" in labels(app.build_node_menu("gen_pw")))

    # exclusive with Ignore
    app.toggle_ignore_node("gen_pw")
    check("Ignore clears Skip", gen.get("ignored") is True and "skipped" not in gen)
    app.toggle_skip_node("gen_pw")
    check("Skip clears Ignore", gen.get("skipped") is True and "ignored" not in gen)

    # ---- saved with the project
    data = json.loads(project_file.dumps_workspace([{"title": "t", "language": "python", "nodes": tab["nodes"], "active_node_id": "ui"}], 0))
    files = project_file.parse_workspace_data(data, {"python"})[0]
    check("project save/load keeps skipped", find_node_by_id(files[0]["nodes"], "gen_pw").get("skipped") is True)
    meta = portable.build_metadata(tab["nodes"], "python", "ui")
    check("metadata carries skipped", meta["nodes"]["gen_pw"].get("skipped") is True and "skipped" not in meta["nodes"]["ui"])
    # embedded round trip via the real pipeline
    full = app.generate_portable_for_tab(tab, "python", embed_meta=True)
    res = portable.rebuild_nodes(full, "python")
    got = {n["id"]: n for n in res[0]} if isinstance(res, tuple) else {}
    check("skipped survives the embedded round trip", got.get("gen_pw", {}).get("skipped") is True)

    # ---- multi-select
    app.toggle_skip_node("gen_pw")                       # un-skip
    check("toggling again clears it", "skipped" not in gen and "text = 'abc'" in code())
    app.selected_nodes = lambda: ["ui", "ui2"]
    app.toggle_skip_node("ui")
    check("multi-select skips them all", ui.get("skipped") and ui2.get("skipped"))
    check("menu names the count", any("2 selected" in l and "Stop skipping" in l for l in labels(app.build_node_menu("ui"))))

    # ---- richer cases: multi-line skipped node, a call nested in an if, brace language
    ui.pop("skipped", None); ui2.pop("skipped", None)          # back to normal nodes
    app.toggle_skip_node("gen_pw") if not gen.get("skipped") else None
    gen["skipped"] = True
    multi = make_node("multi", node_id="multi", blocks=[
        ("assign_variable", {"variable": "a", "value": "1"}),
        ("if_statement", {"condition": "a", "_children": [("print_output", {"value": "a"})]})])
    multi["skipped"] = True
    nest = make_node("nest", node_id="nest", blocks=[
        ("if_statement", {"condition": "True", "_children": [("func_call", {"name": "gen_pw", "args": ""}),
                                                            ("print_output", {"value": "'in'"})]})])
    tab["nodes"] += [multi, nest]; normalize_orders(tab["nodes"])
    c = code()
    check("multi-line skipped node: every line is commented", "## a = 1" in c and "## if a:" in c and "##     print(a)" in c)
    check("call nested in an if is commented, sibling stays live",
          "    ## gen_pw()" in c and "    print('in')" in c)
    exec(compile(c, "<gen>", "exec"), {})
    check("the whole generated file still runs", True)
    check("language comment token drives the marker", app._comment_out("x = 1\n", "cpp") == "//// x = 1\n"
          and app._comment_out("a\n\nb\n", "python") == "## a\n##\n## b\n")
    check("html comment style", app._comment_out("<p>x</p>\n", "html").startswith("<!--"))

    # ---- a container whose only child is a call to a skipped node stays valid
    only = make_node("only", node_id="only", blocks=[
        ("if_statement", {"condition": "True", "_children": [("func_call", {"name": "gen_pw", "args": ""})]}),
        ("print_output", {"value": "'after'"})])
    tab["nodes"].append(only); normalize_orders(tab["nodes"])
    c2 = code()
    check("comment-only container body gets 'pass' and the comment follows",
          "if True:\n    pass\n## gen_pw()\nprint('after')" in c2)
    exec(compile(c2, "<gen2>", "exec"), {})
    check("and the file still runs", True)
    check("stored blocks never get the internal marker",
          "_skip_comment" not in json.dumps([n["blocks"] for n in tab["nodes"]]))
    tab["nodes"].remove(only)

    # ---- code panel: edits inside skipped regions are not synced (and say so)
    notes = []
    app.maybe_notify = lambda *a, **k: notes.append(a)
    app.save_app_settings = lambda: None
    import ui_codesync
    ui_codesync.messagebox.showwarning = lambda *a, **k: notes.append(a)
    ui_codesync.messagebox.showinfo = lambda *a, **k: notes.append(a)
    app.settings.update(show_markers=True, safe_mode=True, code_edit_warned=True,
                        code_sync_mode="manual", code_sync_confirm=True, save_format="sidecar")
    app.update_generated_code() if hasattr(app, "update_generated_code") else None
    app.update()
    txt = app.code_text.get("1.0", "end-1c")
    check("panel shows the commented skipped node between its markers", "## text = 'abc'" in txt and "$$$blockliner:node:gen_pw$$$" in txt)
    before = [list(n["blocks"]) for n in tab["nodes"]]
    def edit_line(needle, new):
        ln = next(i + 1 for i, l in enumerate(app.code_text.get("1.0", "end-1c").split("\n")) if needle in l)
        app.code_text.delete(f"{ln}.0", f"{ln}.end"); app.code_text.insert(f"{ln}.0", new)
    edit_line("## text = 'abc'", "## text = 'xyz'")
    plan = app.compute_sync_plan()
    check("edit inside a skipped node is frozen, not planned", plan["status"] == "ok" and "gen_pw" in plan["frozen"]
          and not [e for e in plan["nodes"] if e["node"] is gen])
    app.run_code_sync(manual=True)
    check("blocks of the skipped node are untouched", gen["blocks"] == [("assign_variable", {"variable": "text", "value": "'abc'"})])
    check("the user is told it was not synced", any("not synced" in " ".join(map(str, n)) for n in notes))
    edit_line("## text = 'xyz'", "## text = 'abc'")             # put it back
    edit_line("print('two')", "print('changed')")              # ui2 does not touch the skipped node
    plan = app.compute_sync_plan()
    check("a node that does not touch skipped code still syncs", [e["node"]["id"] for e in plan["nodes"]] == ["ui2"] and not plan["frozen"])
    edit_line("print('hello')", "print('changed2')")            # ui calls the skipped node
    plan = app.compute_sync_plan()
    check("a node that CALLS the skipped one is frozen too", "ui" in plan["frozen"] and "ui" not in [e["node"]["id"] for e in plan["nodes"]])

    # ---- class/category nodes get no Skip entry
    cat = make_node("grp", node_id="grp", kind="category"); tab["nodes"].append(cat)
    check("category has no Skip", not any("kip" in l for l in labels(app.build_node_menu("grp"))))
    app.destroy()

main()
print("FAILED:", FAILURES) if FAILURES else print("ALL OK")
sys.exit(1 if FAILURES else 0)
