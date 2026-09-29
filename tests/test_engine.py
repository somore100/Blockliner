"""
Run directly (`python tests/test_engine.py` from the V2/ folder) to
prove the new engine works end-to-end: JSON loading + schema
validation + template rendering + nested container blocks - the same
things the old importlib/exec_module + generate_code() system did,
now with zero eval/exec anywhere.
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.loader import load_all_language_packs, load_language_pack, load_master_concepts
from engine.markers import parse_marked_file, reconcile_file
from engine.model import BlockInstance, BlocklinerFile, Node, Project, Workspace
from engine.renderer import render_file, render_node_with_marker, render_project

V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_node_hierarchy(python_blocks):
    """
    Phase A1: Node/BlocklinerFile/Workspace are additive - BlockInstance
    and Project are untouched, and a Node's `.blocks` is shaped exactly
    like Project.blocks, so render_project() works on a Node with zero
    changes via duck typing (it only ever reads `.blocks`).
    """
    node = Node(
        node_id=800,
        node_type="function",
        name="health",
        blocks=[
            BlockInstance("assign_variable", {"variable": "x", "value": "5"}),
            BlockInstance("raw_code", {"code": "print(x)"}),
        ],
    )
    node_code = render_project(node, python_blocks)

    equivalent_project = Project()
    equivalent_project.add_block("assign_variable", {"variable": "x", "value": "5"})
    equivalent_project.add_block("raw_code", {"code": "print(x)"})
    project_code = render_project(equivalent_project, python_blocks)

    assert node_code == project_code == "x = 5\nprint(x)\n", (
        f"Node did not render identically to an equivalent Project!\n"
        f"node: {node_code!r}\nproject: {project_code!r}"
    )

    # Defaults: node_id/node_type/name are the only required fields
    bare_node = Node(node_id=1, node_type="start", name="main")
    assert bare_node.blocks == []
    assert bare_node.references == []
    assert bare_node.raw_span is None
    assert bare_node.category is None

    # raw_span nodes: blocks stays empty, span holds the unmatched text -
    # matches the raw_code block's "honest escape hatch" philosophy,
    # promoted to node granularity for Phase E cold import.
    raw_node = Node(node_id=2, node_type="raw", name="unmatched", raw_span="while True: pass")
    assert raw_node.blocks == []
    assert raw_node.raw_span == "while True: pass"

    # BlocklinerFile / Workspace: plain containers, empty-safe defaults
    bfile = BlocklinerFile(filename="main.py", language="python", nodes=[node, bare_node])
    assert bfile.nodes == [node, bare_node]
    workspace = Workspace(files=[bfile])
    assert workspace.files[0].filename == "main.py"
    assert Workspace().files == []  # default-construction doesn't blow up

    print("\u2713 Phase A1 node hierarchy: Node/BlocklinerFile/Workspace all check out.")


def test_a2_warn_and_strip_contract():
    """
    Phase A2 regression test: a bad 'match' rule, a bad node_types.json
    entry, or a bad comment_token must each degrade gracefully (warned
    and stripped) rather than taking the whole pack - or even just the
    one block - down with them. Runs against a scratch copy of the
    python pack so the real language packs on disk are never touched.
    """
    tmp = tempfile.mkdtemp()
    try:
        pack_dir = os.path.join(tmp, "brokentest")
        shutil.copytree(os.path.join(V2_ROOT, "languages", "python"), pack_dir)

        manifest_path = os.path.join(pack_dir, "manifest.json")
        manifest = json.load(open(manifest_path))
        manifest["comment_token"] = 42  # wrong type
        json.dump(manifest, open(manifest_path, "w"))

        assign_path = os.path.join(pack_dir, "blocks", "assign_variable.json")
        assign_def = json.load(open(assign_path))
        assign_def["match"] = {"node_kind": 123}  # wrong type + missing slot_map
        json.dump(assign_def, open(assign_path, "w"))

        node_types_path = os.path.join(pack_dir, "node_types.json")
        json.dump(
            [
                {"id": "function", "node_kind": "function_definition",
                 "header_template": "def [[name]]([[params]]):", "is_entry_point": False},
                {"id": "broken_missing_field"},  # missing is_entry_point
                "not_even_a_dict",
            ],
            open(node_types_path, "w"),
        )

        manifest_out, blocks_out = load_language_pack(pack_dir, verbose=False)

        assert manifest_out is not None, "pack must still load despite the bad optional fields"
        assert "comment_token" not in manifest_out, "bad comment_token must be stripped, not left in place"
        # Derived from the source pack, not a literal: a hardcoded count
        # has gone stale twice already (rename leftovers, new blocks).
        expected_blocks = len([
            f for f in os.listdir(os.path.join(V2_ROOT, "languages", "python", "blocks"))
            if f.endswith(".json")
        ])
        assert len(blocks_out) == expected_blocks, (
            f"no block may be dropped over a bad match rule, "
            f"got {len(blocks_out)} of {expected_blocks}"
        )
        assert "match" not in blocks_out["assign_variable"], "assign's broken match must be stripped"
        assert "match" in blocks_out["print_output"], "print's valid match must survive untouched"
        assert manifest_out["node_types"] == [
            {"id": "function", "node_kind": "function_definition",
             "header_template": "def [[name]]([[params]]):", "is_entry_point": False}
        ], "only the one valid node_types entry should survive"
    finally:
        shutil.rmtree(tmp)

    print("\u2713 Phase A2 warn-and-strip contract: bad match/node_types/comment_token all degrade gracefully.")


def test_a3_marker_roundtrip(python_blocks):
    """
    Phase A3 test gates, both from the plan verbatim:
      1. Open a Blockliner-generated file, edit nothing, reopen -> byte-identical.
      2. Edit inside markers by hand, reopen -> that node correctly demotes
         to raw, rest of file unaffected.
    """
    comment_token = "#"

    node_a = Node(
        node_id=800, node_type="function", name="health",
        blocks=[BlockInstance("assign_variable", {"variable": "x", "value": "5"})],
    )
    node_b = Node(
        node_id=801, node_type="function", name="damage",
        blocks=[BlockInstance("assign_variable", {"variable": "y", "value": "10"})],
    )
    original_file = BlocklinerFile(filename="game.py", language="python", nodes=[node_a, node_b])

    exported_text = render_file(original_file, python_blocks, comment_token)
    assert "$$$blockliner:node:800$$$ start" in exported_text
    assert "$$$blockliner:node:801$$$ start" in exported_text

    # --- Gate 1: no-op reopen is byte-identical ---
    reconciled_file, diagnostics = reconcile_file(original_file, exported_text, python_blocks)
    assert diagnostics == [], f"no-op reopen produced unexpected diagnostics: {diagnostics}"
    assert reconciled_file.nodes[0] is node_a, "unchanged node must be reattached as the SAME object, not rebuilt"
    assert reconciled_file.nodes[1] is node_b
    re_exported_text = render_file(reconciled_file, python_blocks, comment_token)
    assert re_exported_text == exported_text, "re-exporting an untouched reopen must be byte-identical"

    # --- Gate 2: hand-edit inside node_a's markers only ---
    hand_edited_text = exported_text.replace("x = 5", "x = 999  # hand-edited!")
    reconciled_file2, diagnostics2 = reconcile_file(original_file, hand_edited_text, python_blocks)
    assert len(diagnostics2) == 1 and "800" in diagnostics2[0], f"expected exactly one diagnostic about node 800, got {diagnostics2}"

    edited_node = reconciled_file2.nodes[0]
    assert edited_node.node_id == 800
    assert edited_node.node_type == "raw", "hand-edited node must demote to raw"
    assert edited_node.raw_span == "x = 999  # hand-edited!\n"
    assert edited_node.blocks == [], "demoted node must not retain a stale block tree"

    untouched_node = reconciled_file2.nodes[1]
    assert untouched_node is node_b, "node_b must be completely unaffected by node_a's hand-edit"

    print("\u2713 Phase A3 marker round-trip: no-op reopen is byte-identical, hand-edit demotes only the touched node.")


def test_a3_malformed_markers_never_crash(python_blocks):
    """
    Phase A3 robustness: garbled marker structure must degrade
    gracefully (diagnostics, best-effort segments) - never raise.
    """
    node_a = Node(node_id=1, node_type="function", name="a", blocks=[BlockInstance("assign_variable", {"variable": "x", "value": "1"})])
    original_file = BlocklinerFile(filename="f.py", language="python", nodes=[node_a])

    # Unclosed marker
    text = "# $$$blockliner:node:1$$$ start\nx = 1\n"
    _, diagnostics = reconcile_file(original_file, text, python_blocks)
    assert any("never closed" in d for d in diagnostics)

    # Orphan node id with no corresponding original node
    text2 = "# $$$blockliner:node:999$$$ start\nsomething()\n# $$$blockliner:node:999$$$ end\n"
    reconciled, diagnostics2 = reconcile_file(original_file, text2, python_blocks)
    assert any("999" in d and "not in the project" in d for d in diagnostics2)
    assert reconciled.nodes[0].node_type == "raw" and reconciled.nodes[0].node_id == 999

    # Mismatched start/end ids
    text3 = "# $$$blockliner:node:1$$$ start\nx = 1\n# $$$blockliner:node:2$$$ end\n"
    _, diagnostics3 = reconcile_file(original_file, text3, python_blocks)
    assert any("mismatch" in d for d in diagnostics3)

    print("\u2713 Phase A3 malformed markers: unclosed/orphan/mismatched all degrade gracefully, nothing raised.")


def main():
    master_concepts = load_master_concepts(os.path.join(V2_ROOT, "concepts.json"), verbose=True)
    print(f"Master concepts loaded: {len(master_concepts)} -> {sorted(master_concepts)}\n")

    packs = load_all_language_packs(os.path.join(V2_ROOT, "languages"), verbose=True)
    assert "python" in packs, "python language pack failed to load"
    python_blocks = packs["python"]["blocks"]
    print()

    # Build a small project: assign x, an if-block containing a print
    # and a list_append, plus a raw_code escape-hatch block.
    project = Project()
    project.add_block("assign_variable", {"variable": "x", "value": "5"})
    project.add_block("list_create", {"variable": "my_list", "items": "1, 2, 3"})
    project.add_block(
        "if_statement",
        {"condition": "x > 3"},
        children=[
            BlockInstance("print_output", {"value": "x", }),
            BlockInstance("list_append", {"list": "my_list", "item": "x"}),
        ],
    )
    project.add_block("raw_code", {"code": "print('done')"})

    code = render_project(project, python_blocks)
    print("--- Rendered Python source ---")
    print(code)
    print("-------------------------------")

    expected = (
        "x = 5\n"
        "my_list = [1, 2, 3]\n"
        "if x > 3:\n"
        "    print(x)\n"
        "    my_list.append(x)\n"
        "print('done')\n"
    )
    assert code == expected, f"Mismatch!\n--- got ---\n{code!r}\n--- expected ---\n{expected!r}"
    print("\u2713 All assertions passed - engine renders correctly, no eval/exec used.")

    test_node_hierarchy(python_blocks)
    test_a2_warn_and_strip_contract()
    test_a3_marker_roundtrip(python_blocks)
    test_a3_malformed_markers_never_crash(python_blocks)


if __name__ == "__main__":
    main()
