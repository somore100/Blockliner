"""Wire kinds (call / data / import): derived, never stored, one style table.
Pure rules (wire_kinds.py) + what the canvas actually draws. Headless (Xvfb)."""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wire_kinds as wk
import project_file
from nodes_model import make_node, normalize_orders, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def chip(name, args=""):
    return {"_nested_block": "func_call", "_nested_params": {"name": name, "args": args}}

def main():
    # ---------------- pure: styles
    check("three kinds", wk.KINDS == ("call", "data", "import"))
    check("every kind has a style with colour/dash/width", all(
        set(wk.STYLES[k]) == {"color", "dash", "width"} for k in wk.KINDS))
    check("the three colours differ", len({wk.STYLES[k]["color"] for k in wk.KINDS}) == 3)
    check("the three looks differ (colour, dash)", len({(wk.STYLES[k]["color"], wk.STYLES[k]["dash"]) for k in wk.KINDS}) == 3)
    check("call is solid (as before)", wk.STYLES["call"]["dash"] is None and wk.STYLES["call"]["color"] == "#6a9955")
    check("data and import are dashed/dotted", wk.STYLES["data"]["dash"] and wk.STYLES["import"]["dash"])
    sel = wk.style_for("data", selected=True)
    check("selected: orange + thicker, dash of the kind kept",
          sel["color"] == "#e8a33d" and sel["width"] == 3 and sel["dash"] == wk.STYLES["data"]["dash"])
    check("selected call stays solid", wk.style_for("call", True)["dash"] is None)
    check("unknown kind looks like a call", wk.style_for("???") == wk.style_for("call") and wk.style_for(None) == wk.style_for("call"))
    st = wk.style_for("call"); st["color"] = "x"
    check("style_for returns a copy", wk.STYLES["call"]["color"] == "#6a9955")

    # ---------------- pure: call_kinds
    ck = wk.call_kinds
    check("plain call block = call", ck([("func_call", {"name": "f", "args": ""})]) == {"f": "call"})
    check("result assigned = data", ck([("assign_variable", {"variable": "x", "value": chip("f")})]) == {"f": "data"})
    check("printed result = data", ck([("print_output", {"value": chip("f")})]) == {"f": "data"})
    check("plain AND result use = data", ck([("func_call", {"name": "f"}), ("assign_variable", {"variable": "x", "value": chip("f")})]) == {"f": "data"})
    check("order does not matter", ck([("assign_variable", {"variable": "x", "value": chip("f")}), ("func_call", {"name": "f"})]) == {"f": "data"})
    check("two callees, two kinds", ck([("func_call", {"name": "a"}), ("print_output", {"value": chip("b")})]) == {"a": "call", "b": "data"})
    inner = [("if_statement", {"condition": "c", "_children": [("print_output", {"value": chip("deep")}), ("func_call", {"name": "p"})]})]
    check("inside containers", ck(inner) == {"deep": "data", "p": "call"})
    check("chip inside a chip's arguments", ck([("print_output", {"value": {"_nested_block": "func_call",
          "_nested_params": {"name": "outer", "args": chip("innerc")}}})]) == {"outer": "data", "innerc": "data"})
    check("chip inside a plain call's args: outer call, inner data",
          ck([("func_call", {"name": "outer", "args": chip("innerc")})]) == {"outer": "call", "innerc": "data"})
    check("chip in a list value", ck([("x", {"value": [chip("l1"), "t"]})]) == {"l1": "data"})
    check("blank names ignored", ck([("func_call", {"name": "  "}), ("p", {"value": chip("")})]) == {})
    check("junk does not crash", ck([None, ("func_call", None), ("x", {"value": 5}), ("y", {"_children": None}), 7, ("z",)]) == {})
    check("empty / None", ck([]) == {} and ck(None) == {})
    src = [("assign_variable", {"variable": "x", "value": chip("f")})]
    frozen = copy.deepcopy(src); ck(src)
    check("input untouched", src == frozen)
    check("non-call chips are not calls", ck([("x", {"value": {"_nested_block": "len_of", "_nested_params": {"name": "f"}}})]) == {})

    # ---------------- UI: call wires
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    plain = make_node("plain_t", node_id="plain_t", blocks=[("print_output", {"value": "'p'"})])
    resu = make_node("result_t", node_id="result_t", blocks=[("print_output", {"value": "'r'"})])
    both = make_node("both_t", node_id="both_t", blocks=[("print_output", {"value": "'b'"})])
    caller = make_node("caller", node_id="caller", blocks=[
        ("func_call", {"name": "plain_t", "args": ""}),
        ("assign_variable", {"variable": "r", "value": chip("result_t")}),
        ("func_call", {"name": "both_t", "args": ""}),
        ("print_output", {"value": chip("both_t")})])
    gen = make_node("gen", node_id="gen", blocks=[("assign_variable", {"variable": "txt", "value": "'a'"})])
    user = make_node("user", node_id="user", blocks=[("print_output", {"value": "txt"})])
    nodes = [plain, resu, both, caller, gen, user]
    for i, n in enumerate(nodes):
        n["canvas_x"], n["canvas_y"] = 40 + (i % 3) * 330, 60 + (i // 3) * 170
    tab["nodes"] = nodes; normalize_orders(tab["nodes"])
    tab["file_view_path"] = []; app.active_tab_index = 0; app.view_mode = "file"
    app.refresh_workspace(); app.update(); app.update_idletasks()
    c = app.workspace_canvas

    def line_of(tag):
        for i in c.find_withtag(tag):
            if c.type(i) == "line":
                return i
        return None
    def look(tag):
        i = line_of(tag)
        return None if i is None else (c.itemcget(i, "fill"), c.itemcget(i, "dash"), float(c.itemcget(i, "width")))

    check("derived kinds on the caller", caller["ref_kinds"] == {"plain_t": "call", "result_t": "data", "both_t": "data"})
    check("nodes that call nothing have no kinds", plain["ref_kinds"] == {} and user["ref_kinds"] == {})
    check("references unchanged by kinds", sorted(caller["references"]) == ["both_t", "plain_t", "result_t"])
    check("plain call: solid green", look("wire_caller_plain_t") == ("#6a9955", "", 2.0))
    check("result used: dashed blue", look("wire_caller_result_t") == ("#4f8fd6", "6 4", 2.0))
    check("plain + result: data style", look("wire_caller_both_t") == ("#4f8fd6", "6 4", 2.0))
    check("the dot at the end has the kind's colour", any(c.type(i) == "oval" and c.itemcget(i, "fill") == "#4f8fd6"
          for i in c.find_withtag("wire_caller_result_t")))
    check("variable data wire has the data look too", look("dwire_gen_user") == ("#4f8fd6", "6 4", 2.0))

    # still a real call wire: select + delete work
    app.select_wire("caller", "result_t"); app.update()
    check("selected data-kind call wire: orange, thick, still dashed", look("wire_caller_result_t") == ("#e8a33d", "6 4", 3.0))
    app.select_wire("caller", "plain_t"); app.update()
    check("selected plain call wire: orange, thick, solid", look("wire_caller_plain_t") == ("#e8a33d", "", 3.0))
    check("the other wire is back to its own look", look("wire_caller_result_t") == ("#4f8fd6", "6 4", 2.0))
    check("call wire is still bound to select/delete", bool(c.tag_bind("wire_caller_result_t", "<Double-Button-1>")))

    # kind follows the code
    caller["blocks"][1] = ("func_call", {"name": "result_t", "args": ""})
    app.refresh_workspace(); app.update()
    check("result no longer used: wire turns solid green", caller["ref_kinds"]["result_t"] == "call"
          and look("wire_caller_result_t") == ("#6a9955", "", 2.0))
    caller["blocks"][1] = ("assign_variable", {"variable": "r", "value": chip("result_t")})
    app.refresh_workspace(); app.update()
    check("result used again: dashed blue", look("wire_caller_result_t") == ("#4f8fd6", "6 4", 2.0))

    # drag fast path keeps the looks
    caller["canvas_x"] += 30
    app._fileview_selected_wire = None; app.refresh_workspace(); app.update()
    app.draw_wires_for("caller"); app.update()
    check("after a drag the looks are unchanged", look("wire_caller_plain_t") == ("#6a9955", "", 2.0)
          and look("wire_caller_result_t") == ("#4f8fd6", "6 4", 2.0))
    check("no duplicate lines after the drag", sum(1 for i in c.find_withtag("wire_caller_plain_t") if c.type(i) == "line") == 1)

    # never saved
    saved = json.dumps(project_file.build_project_data("python", tab["nodes"], "caller"))
    check("ref_kinds is not saved", "ref_kinds" not in saved)

    # blocks via the port-drop helper: result lands as data kind
    act = make_node("act", node_id="act", blocks=[("func_def", {"name": "act", "params": "", "_children": []})])
    act["canvas_x"], act["canvas_y"] = 700, 200
    tab["nodes"].append(act); normalize_orders(tab["nodes"])
    app.refresh_workspace(); app.update()
    app.add_port_wire("act", "user")
    app.refresh_workspace(); app.update()
    check("a function without outputs dropped on a node: wire is solid (no result)",
          find_node_by_id(tab["nodes"], "user")["ref_kinds"].get("act") == "call"
          and look("wire_user_act") == ("#6a9955", "", 2.0))
    retf = make_node("retf", node_id="retf", blocks=[("func_def", {"name": "retf", "params": "",
           "_children": [("return_statement", {"value": "val"})]})])
    retf["canvas_x"], retf["canvas_y"] = 700, 400
    tab["nodes"].append(retf); normalize_orders(tab["nodes"])
    app.refresh_workspace(); app.update()
    app.add_port_wire("retf", "user"); app.refresh_workspace(); app.update()
    check("a node with an output dropped on a node: wire is data (result is stored)",
          find_node_by_id(tab["nodes"], "user")["ref_kinds"].get("retf") == "data"
          and look("wire_user_retf") == ("#4f8fd6", "6 4", 2.0))

    # ---------------- UI: import wire (Files layer)
    app.new_tab(); app.tabs[1]["title"] = "helpers"
    app.tabs[0]["nodes"][0]["blocks"].append(("import_module", {"module": "helpers"}))
    app.switch_to_files_view(); app.update()
    imp = [i for i in c.find_withtag("file_wire_0_1") if c.type(i) == "line"]
    check("import wire drawn", len(imp) == 1)
    check("import wire: dotted violet", (c.itemcget(imp[0], "fill"), c.itemcget(imp[0], "dash"), float(c.itemcget(imp[0], "width")))
          == ("#b57edc", "2 5", 2.0))
    check("import look differs from call and data looks", c.itemcget(imp[0], "fill") not in ("#6a9955", "#4f8fd6"))
    check("import dot colour", any(c.type(i) == "oval" and c.itemcget(i, "fill") == "#b57edc" for i in c.find_withtag("file_wire_0_1")))
    app.destroy()
    print("FAILURES:", len(FAILURES))
    sys.exit(1 if FAILURES else 0)

main()
