"""Derived DATA wires: node B reads a variable that an earlier def-less node
assigns -> dashed blue wire producer -> user, labelled with the name. Pure
derivation (node_ports.data_wires) + canvas drawing. Headless (Xvfb)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import node_ports as np_
import project_file
from nodes_model import make_node, find_node_by_id
from ui import BlocklinerUI

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def var_node(name, *assigns, extra=()):
    blocks = [("assign_variable", {"variable": v, "value": val}) for v, val in assigns] + list(extra)
    return make_node(name, node_id=name, blocks=blocks)

def printer(name, value):
    return make_node(name, node_id=name, blocks=[("print_output", {"value": value})])

def wires(*nodes):
    return np_.data_wires(list(nodes))

def main():
    # ---- pure
    gen = var_node("gen", ("text", "'abc'"), ("n", "3"))
    check("print of the variable = one wire", wires(gen, printer("show", "text")) == [("gen", "show", ["text"])])
    check("two variables, one wire with both names",
          wires(gen, printer("show", "text + str(n)")) == [("gen", "show", ["text", "n"])])
    check("run order matters: user BEFORE producer = no wire", wires(printer("show", "text"), gen) == [])
    check("same name inside a string literal is not a use", wires(gen, printer("show", "'text'")) == [])
    check('double-quoted literal with an escaped quote', wires(gen, printer("show", r'"a\"text" + other')) == [])
    check("attribute name is not a use (obj.text)", wires(gen, printer("show", "obj.text")) == [])
    check("longer name is not a use (text2)", wires(gen, printer("show", "text2 + _text")) == [])
    check("self never wires to itself", wires(var_node("a", ("x", "1"), ("y", "x + 1"))) == [])
    user_assign = var_node("u", ("text", "'mine'"), extra=[("print_output", {"value": "text"})])
    check("assigned in the user first = its own variable, no wire", wires(gen, user_assign) == [])
    modify = var_node("m", ("text", "text + 'x'"))
    check("x = x + .. reads the producer's x", wires(gen, modify) == [("gen", "m", ["text"])])
    check("nearest earlier producer wins",
          wires(gen, var_node("gen2", ("text", "'z'")), printer("show", "text")) == [("gen2", "show", ["text"])])
    fnn = make_node("check", node_id="check", blocks=[("func_def", {"name": "check", "params": "text",
            "_children": [("return_statement", {"value": "text"})]})])
    check("a function parameter shadows the producer's variable", wires(gen, fnn) == [])
    fn_global = make_node("g", node_id="g", blocks=[("func_def", {"name": "g", "params": "",
            "_children": [("print_output", {"value": "text"})]})])
    check("a function body reading a global gets a wire", wires(gen, fn_global) == [("gen", "g", ["text"])])
    check("a function node does NOT produce its return names as variables",
          wires(fnn, printer("show", "text")) == [])
    fn_extra = make_node("fx", node_id="fx", blocks=[("func_def", {"name": "fx", "params": "", "_children": []}),
            ("assign_variable", {"variable": "extra", "value": "1"})])
    check("a node WITH its function does not produce variables even if it assigns some",
          wires(fn_extra, printer("show", "extra")) == [])
    loop = make_node("l", node_id="l", blocks=[("for_loop", {"variable": "text", "iterable": "items",
            "_children": [("print_output", {"value": "text"})]})])
    check("loop variable of the same name is local", wires(gen, loop) == [])
    nested = make_node("nn", node_id="nn", blocks=[("if_statement", {"condition": "n > 1",
            "_children": [("print_output", {"value": "text"})]})])
    check("uses inside containers count (several names, one wire)", wires(gen, nested) == [("gen", "nn", ["n", "text"])])
    chip = make_node("c", node_id="c", blocks=[("print_output", {"value": {"_nested_block": "func_call",
            "_nested_params": {"name": "text", "args": "n"}}})])
    check("chip: call NAME is not a use, its arguments are", wires(gen, chip) == [("gen", "c", ["n"])])
    check("call block: name is not a use", wires(gen, make_node("k", node_id="k",
          blocks=[("func_call", {"name": "text", "args": ""})])) == [])
    check("category/class nodes are ignored", wires(gen, make_node("cat", kind="category")) == [])
    check("junk blocks do not crash", wires(gen, make_node("j", node_id="j",
          blocks=[None, ("print_output", None), ("print_output", {"value": 5}), ("x", {"value": ["text", None]})]))
          == [("gen", "j", ["text"])])
    check("two producers, two wires", wires(gen, var_node("p2", ("q", "1")), printer("s", "text + q"))
          == [("gen", "s", ["text"]), ("p2", "s", ["q"])])

    # ---- UI
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.save_app_settings = lambda: None; app.maybe_notify = lambda *a, **k: None
    app.geometry("1400x800"); app.update()
    tab = app.tabs[0]
    nodes = [var_node("gen_pw", ("text", "'abc'")), printer("show_pw", "text"),
             printer("other", "'hello'"), var_node("gen_q", ("q", "1")), printer("show_q", "q")]
    for i, n in enumerate(nodes):
        n["canvas_x"], n["canvas_y"] = 60 + i * 300, 80 + i * 20
    tab["nodes"] = nodes
    from nodes_model import normalize_orders
    normalize_orders(tab["nodes"])
    app.active_tab_index = 0
    app.view_mode = "file"; tab["file_view_path"] = []
    app.refresh_workspace(); app.update()
    gen_n, show_n, other_n = (find_node_by_id(tab["nodes"], i) for i in ("gen_pw", "show_pw", "other"))
    check("user node records the producer + names", show_n["data_uses"] == [{"id": "gen_pw", "vars": ["text"]}])
    check("others have none", gen_n["data_uses"] == [] and other_n["data_uses"] == [])
    c = app.workspace_canvas
    check("one dashed blue data wire is drawn", len(c.find_withtag("dwire_gen_pw_show_pw")) == 3
          and any(c.type(i) == "line" and c.itemcget(i, "dash") for i in c.find_withtag("dwire_gen_pw_show_pw")))
    labels = [c.itemcget(i, "text") for i in c.find_withtag("dwire_gen_pw_show_pw") if c.type(i) == "text"]
    check("wire is labelled with the variable name", labels == ["text"])
    check("no call wire invented", not c.find_withtag("wire_gen_pw_show_pw"))
    check("references untouched (no call)", gen_n["references"] == [] and show_n["references"] == [])

    line = [i for i in c.find_withtag("dwire_gen_pw_show_pw") if c.type(i) == "line"][0]
    box = app._fileview_boxes["gen_pw"][1]
    check("data wire leaves a little BELOW the box centre (clear of a call wire)",
          c.coords(line)[1] > gen_n["canvas_y"] * app.canvas_zoom + (box.winfo_height() or 70) / 2)
    check("second pair has its own wire", len(c.find_withtag("dwire_gen_q_show_q")) == 3)

    # code unchanged / not saved
    saved = project_file.build_project_data("python", tab["nodes"], "gen_pw")
    check("data_uses is not saved", "data_uses" not in json.dumps(saved))

    # fast path (drag motion) redraws only that wire
    before = list(c.find_withtag("dwire_gen_pw_show_pw"))
    gen_n["canvas_x"] += 50
    app.draw_wires_for("gen_pw"); app.update()
    after = list(c.find_withtag("dwire_gen_pw_show_pw"))
    check("drag fast path redraws the data wire once (no duplicates)", len(after) == 3 and after != before)
    check("fast path leaves an unrelated data wire alone (no duplicates)",
          len(c.find_withtag("dwire_gen_q_show_q")) == 3)

    # run order flipped -> wire disappears; back -> returns
    show_n["order"], gen_n["order"] = 1, 2
    app.refresh_workspace(); app.update()
    check("user running before the producer: no wire", not c.find_withtag("dwire_gen_pw_show_pw")
          and show_n["data_uses"] == [])
    show_n["order"], gen_n["order"] = 2, 1
    app.refresh_workspace(); app.update()
    check("order restored: wire is back", len(c.find_withtag("dwire_gen_pw_show_pw")) == 3)

    # skipped / ignored producer or user -> no wire
    gen_n["skipped"] = True; app.refresh_workspace(); app.update()
    check("skipped producer: no wire", not c.find_withtag("dwire_gen_pw_show_pw"))
    gen_n.pop("skipped"); show_n["ignored"] = True; app.refresh_workspace(); app.update()
    check("ignored user: no wire", not c.find_withtag("dwire_gen_pw_show_pw"))
    show_n.pop("ignored"); app.refresh_workspace(); app.update()
    check("both live again: wire back", len(c.find_withtag("dwire_gen_pw_show_pw")) == 3)

    # editing the code removes it again (derived from blocks)
    show_n["blocks"] = [("print_output", {"value": "'bye'"})]
    app.refresh_workspace(); app.update()
    check("remove the use in the code: wire gone", not c.find_withtag("dwire_gen_pw_show_pw"))

    # clicking / double-clicking a data wire must not change anything
    show_n["blocks"] = [("print_output", {"value": "text"})]
    app.refresh_workspace(); app.update()
    n_before = (len(gen_n["blocks"]), len(show_n["blocks"]))
    check("data wire has no delete binding", not c.tag_bind("dwire_gen_pw_show_pw", "<Double-Button-1>"))
    check("blocks untouched", n_before == (1, 1))

    # zoomed far out (compact boxes) still draws without error
    app.set_zoom(0.3); app.update(); app.update_idletasks()
    check("compact zoom keeps the data wire", len(c.find_withtag("dwire_gen_pw_show_pw")) == 3)
    app.destroy()
    print("FAILURES:", len(FAILURES))
    sys.exit(1 if FAILURES else 0)

main()
