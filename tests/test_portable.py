"""Pure tests for portable.py (no Tk): markers, metadata block, strip,
parse, skeleton rebuild, fallback placement, damaged input."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import portable as P

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def node(i, name, kind="function", children=None, **kw):
    n = {"id": i, "name": name, "kind": kind, "child_nodes": children or [], "blocks": [], "locked": False}
    n.update(kw); return n

def build(tokens="#", indent=""):
    nodes = [node("a1", "first", order=1, canvas_x=40, canvas_y=60),
             node("b2", "second", order=2, canvas_x=300, canvas_y=60)]
    meta = P.build_metadata(nodes, "python", "a1")
    chunks = []
    for n, body in zip(nodes, ["x = 1\n", "print(x)\n"]):
        s, e = P.node_marker_lines(n["id"], tokens)
        chunks.append((s, indent + body, e, indent))
    return nodes, P.assemble("", chunks, "", P.render_meta_block(meta, tokens)), meta

def main():
    nodes, text, meta = build()
    clean = "x = 1\nprint(x)\n"
    check("strip(portable) == plain code", P.strip_portable(text) == clean)
    check("strip on plain text is a no-op", P.strip_portable(clean) == clean)
    check("node marker carries only the id", "# $$$blockliner:node:a1$$$ start" in text and text.count("$$$blockliner:node:") == 4)
    check("meta delimiters present", "$$$blockliner:meta$$$" in text and text.rstrip().endswith("$$$blockliner:meta:end$$$"))

    got, m, diag = P.parse_portable(text)
    check("parse finds nodes in order with code", [(n["id"], n["code"]) for n in got] == [("a1", "x = 1\n"), ("b2", "print(x)\n")])
    check("parse reads metadata, no diagnostics", m and m["nodes"]["a1"]["x"] == 40 and diag == [])

    top, active, diag = P.rebuild_nodes(text, "python")
    check("rebuild restores names, order, positions", [(n["name"], n["order"], n["canvas_x"]) for n in top] == [("first", 1, 40), ("second", 2, 300)])
    check("rebuild keeps code per node and active id", top[0]["code"] == "x = 1\n" and active == "a1")
    check("saved positions are not flagged as fallback", all("_auto_pos" not in n for n in top))

    # nesting + kinds + category via metadata
    tree = [node("c1", "Program", "class", children=[node("m1", "main", order=1, locked=True, node_type_id="start")], locked=True),
            node("g1", "Folder", "category", children=[node("f2", "helper", order=2)])]
    meta2 = P.build_metadata(tree, "csharp", "m1")
    s1, e1 = P.node_marker_lines("m1", "//"); s2, e2 = P.node_marker_lines("f2", "//")
    text2 = P.assemble("class Program {\n", [(s1, "    a();\n", e1, "    "), (s2, "    b();\n", e2, "    ")], "}\n", P.render_meta_block(meta2, "//"))
    top, active, diag = P.rebuild_nodes(text2, "csharp", "    ", "class Program {\n}\n")
    check("class keeps its child, category keeps its child", top[0]["kind"] == "class" and top[0]["child_nodes"][0]["id"] == "m1" and top[1]["kind"] == "category" and top[1]["child_nodes"][0]["id"] == "f2")
    check("wrapper indent removed from node code", top[0]["child_nodes"][0]["code"] == "a();\n")
    check("expected wrapper text raises no note", diag == [])
    check("locked and node_type_id restored", top[0]["locked"] and top[0]["child_nodes"][0]["node_type_id"] == "start")

    # no metadata -> flat skeleton, file order, grid fallback, nothing invented
    bare = P.strip_portable(text.replace("# $$$blockliner:meta$$$", "# nothing")) if False else "".join(l for l in text.splitlines(True)[:6])
    top, active, diag = P.rebuild_nodes(bare, "python")
    check("no metadata: flat skeleton named by id", [(n["id"], n["name"], n["kind"]) for n in top] == [("a1", "a1", "function"), ("b2", "b2", "function")])
    check("no metadata: order = file position", [n["order"] for n in top] == [1, 2])
    check("no metadata: no parents, no references invented", all(n["child_nodes"] == [] and n["references"] == [] for n in top))
    check("fallback grid is deterministic and spreads nodes", (top[0]["canvas_x"], top[0]["canvas_y"]) == P.grid_position(0) and top[0]["canvas_x"] != top[1]["canvas_x"])
    check("fallback positions flagged as heuristic", top[0]["_auto_pos"] == (top[0]["canvas_x"], top[0]["canvas_y"]))
    check("active falls back to first function node", active == "a1")
    meta3 = P.build_metadata(top, "python")
    check("fallback positions NOT written back as layout", "x" not in meta3["nodes"]["a1"] and "x" not in meta3["nodes"]["b2"])
    top[0]["canvas_x"] += 50
    check("a moved node's position IS saved", P.build_metadata(top, "python")["nodes"]["a1"]["x"] == top[0]["canvas_x"])
    many = "".join(f"# $$$blockliner:node:n{i}$$$ start\nv{i}\n# $$$blockliner:node:n{i}$$$ end\n" for i in range(7))
    top, _, _ = P.rebuild_nodes(many, "python")
    check("7 skeleton nodes all get distinct positions", len({(n["canvas_x"], n["canvas_y"]) for n in top}) == 7)

    # damaged metadata -> reported, skeleton still built
    broken = text.replace('"v": 1', '"v": 1,,')
    top, _, diag = P.rebuild_nodes(broken, "python")
    check("bad JSON reported, skeleton used", len(top) == 2 and any("not valid JSON" in d for d in diag) and top[0]["name"] == "a1")
    unclosed = text.replace("# $$$blockliner:meta:end$$$", "# oops")
    top, _, diag = P.rebuild_nodes(unclosed, "python")
    check("unclosed metadata reported, nodes still found", len(top) == 2 and any("never closed" in d for d in diag))
    check("strip on unclosed metadata still removes it", "blockliner:meta" not in P.strip_portable(unclosed))

    # metadata vs markers disagreements
    lost = text.replace("# $$$blockliner:node:b2$$$ start", "").replace("# $$$blockliner:node:b2$$$ end", "")
    top, _, diag = P.rebuild_nodes(lost, "python")
    check("node in metadata without markers restored empty + reported", [n["id"] for n in top] == ["a1", "b2"] and top[1]["code"] == "" and any("no markers" in d for d in diag))
    extra = text.replace("# $$$blockliner:meta$$$", "# $$$blockliner:node:zz$$$ start\nq\n# $$$blockliner:node:zz$$$ end\n\n# $$$blockliner:meta$$$", 1)
    top, _, diag = P.rebuild_nodes(extra, "python")
    check("marker not in metadata added as plain node + reported", "zz" in [n["id"] for n in top] and any("not in the metadata" in d for d in diag))
    cyc = json.loads(json.dumps(meta)); cyc["nodes"]["a1"]["parent"] = "b2"; cyc["nodes"]["b2"]["parent"] = "a1"
    cyc_text = text.split("\n\n# $$$blockliner:meta$$$")[0] + "\n\n" + P.render_meta_block(cyc, "#")
    top, _, diag = P.rebuild_nodes(cyc_text, "python")
    check("cyclic/function parents are not trusted (top level)", [n["id"] for n in top] == ["a1", "b2"] and any("unusable parent" in d for d in diag))

    fp = json.loads(json.dumps(meta)); fp["nodes"]["b2"]["parent"] = "a1"   # a1 is a function node
    fp_text = text.split("\n\n# $$$blockliner:meta$$$")[0] + "\n\n" + P.render_meta_block(fp, "#")
    top, _, diag = P.rebuild_nodes(fp_text, "python")
    check("a function node is never used as a parent", [n["id"] for n in top] == ["a1", "b2"] and top[0]["child_nodes"] == [])
    sp = json.loads(json.dumps(meta)); sp["nodes"]["a1"]["parent"] = "a1"
    sp_text = text.split("\n\n# $$$blockliner:meta$$$")[0] + "\n\n" + P.render_meta_block(sp, "#")
    top, _, diag = P.rebuild_nodes(sp_text, "python")
    check("self-parent does not loop and stays top level", [n["id"] for n in top] == ["a1", "b2"])
    cats = [node("k1", "A", "category"), node("k2", "B", "category"), node("a1", "first", order=1)]
    cm = P.build_metadata(cats, "python")
    cm["nodes"]["k1"]["parent"] = "k2"; cm["nodes"]["k2"]["parent"] = "k1"; cm["nodes"]["a1"]["parent"] = "k1"
    cat_text = P.assemble("", [(*P.node_marker_lines("a1", "#")[:1], "x\n", P.node_marker_lines("a1", "#")[1], "")], "", P.render_meta_block(cm, "#"))
    top, _, diag = P.rebuild_nodes(cat_text, "python")
    ids = lambda lvl: sorted(n["id"] for n in lvl)
    check("category parent cycle terminates, cycle nodes stay top level", {"k1", "k2"} <= set(ids(top)) and any("unusable parent" in d for d in diag))
    gone = json.loads(json.dumps(meta)); gone["nodes"]["b2"]["parent"] = "does-not-exist"
    gone_text = text.split("\n\n# $$$blockliner:meta$$$")[0] + "\n\n" + P.render_meta_block(gone, "#")
    top, _, diag = P.rebuild_nodes(gone_text, "python")
    check("missing parent: node kept at top level, reported", [n["id"] for n in top] == ["a1", "b2"] and any("unusable parent" in d for d in diag))

    # mismatched / duplicate markers never raise
    messy = "# $$$blockliner:node:a$$$ start\n1\n# $$$blockliner:node:b$$$ start\n2\n# $$$blockliner:node:b$$$ end\n# $$$blockliner:node:a$$$ end\n# $$$blockliner:node:b$$$ start\n3\n# $$$blockliner:node:b$$$ end\n"
    got, _, diag = P.parse_portable(messy)
    check("overlap/duplicates: no crash, notes, first duplicate kept", [n["id"] for n in got] == ["a", "b"] and len(diag) >= 2)
    check("stray end marker ignored", P.parse_portable("# $$$blockliner:node:x$$$ end\ncode\n")[0] == [])
    check("outside text is reported not turned into nodes", any("outside any node" in d for d in P.parse_portable("hello\n# $$$blockliner:node:x$$$ start\n1\n# $$$blockliner:node:x$$$ end\n")[2]))

    # order: absent key is written as its tree position; explicit None kept
    on = [node("p", "p"), node("q", "q", order=None), node("r", "r", order=7)]
    om = P.build_metadata(on, "python")["nodes"]
    check("absent order written as tree position, None and numbers kept", om["p"]["order"] == 1 and om["q"]["order"] is None and om["r"]["order"] == 7)

    # HTML comments + '--' in names
    hn = [node("h1", "a--b -->", order=1)]
    hm = P.build_metadata(hn, "html")
    block = P.render_meta_block(hm, ["<!--", "-->"])
    check("HTML meta lines contain no early comment close", all(l.count("-->") == 1 and l.rstrip().endswith("-->") for l in block.splitlines()))
    s, e = P.node_marker_lines("h1", ["<!--", "-->"])
    htext = P.assemble("", [(s, "<p>x</p>\n", e, "")], "", block)
    top, _, diag = P.rebuild_nodes(htext, "html")
    check("HTML round trip keeps tricky name", top[0]["name"] == "a--b -->" and diag == [])
    check("HTML strip == plain", P.strip_portable(htext) == "<p>x</p>\n")

    # empty node still marked
    s, e = P.node_marker_lines("e1", "#")
    et = P.assemble("", [(s, "", e, "")], "")
    check("empty node survives round trip", [n["id"] for n in P.parse_portable(et)[0]] == ["e1"] and P.strip_portable(et) == "")

    print("FAILURES:", FAILURES)
    sys.exit(1 if FAILURES else 0)

main()
