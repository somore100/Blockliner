"""Scripted UI test (run under Xvfb): every Python block's code turns back into the same block (so typed code
and pasted code are recognised), params and bodies survive, realistic lines go to the right block, and a program
written with the new blocks reads back, regenerates identical code and runs."""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI
from ui_common import get_block_attr

FAILURES = []
SKIP = {"raw_code", "node_output", "node_input", "return_statement", "divider", "comment"}      # no code of their own to match, or older special cases


def check(label, cond):
    if not cond:
        print(f"[FAIL] {label}")
        FAILURES.append(label)
    else:
        print(f"[OK] {label}")


def settle(app):
    for _ in range(3):
        app.update_idletasks()
        app.update()


def code_of(app, node, blocks):
    node["blocks"][:] = blocks
    app.update_generated_code()
    return app.get_clean_code()


def main():
    app = BlocklinerUI(initial_lang="python", languages_path="languages")
    app.geometry("1300x800+0+0")
    try:
        settle(app)
        node = app.get_active_node(app.tabs[app.active_tab_index])
        bad_id, bad_params, bad_body = [], [], []
        total = 0
        for bid, mod in sorted(app.blocks.items()):
            if bid in SKIP or bid.startswith("ui_"):
                continue
            total += 1
            params = {p["name"]: p.get("default", "") for p in get_block_attr(mod, "params", [])}
            container = bool(get_block_attr(mod, "is_container", False))
            if container:
                params["_children"] = [("print_output", {"value": "1"})]
            code = code_of(app, node, [(bid, params)])
            blocks, _matched, _raw = app.import_code_to_blocks(code)
            back = [b for b in blocks if b[0] != "import_module" or bid == "import_module"]          # blocks that need a module add its import first
            if not back or back[0][0] != bid:
                bad_id.append((bid, code.strip().replace("\n", " | "), [b[0] for b in blocks][:3]))
                continue
            got = {k: v for k, v in back[0][1].items() if k != "_children"}
            want = {k: v for k, v in params.items() if k != "_children"}
            if got != want:
                bad_params.append((bid, want, got))
            if container and not [c for c in back[0][1].get("_children", []) if c[0] == "print_output"]:
                bad_body.append(bid)
        check(f"all {total} blocks come back as themselves from their own code {bad_id}", not bad_id)
        check(f"...with their values intact {bad_params}", not bad_params)
        check(f"...and containers keep their body {bad_body}", not bad_body)

        # lines people actually type must go to the right block
        expect = [
            ("total += 5", "change_variable"), ("count -= 1", "change_variable"), ("x **= 2", "change_variable"),
            ("age = int(text)", "convert_type"), ("n = len(items)", "length_of"),
            ("scores = {\"a\": 1}", "dict_create"), ("scores[\"b\"] = 2", "item_set"), ("v = scores[\"b\"]", "item_get"),
            ("names = [\"a\", \"b\"]", "list_create"), ("names.append(\"c\")", "list_append"), ("names.sort()", "list_sort"),
            ("last = names.pop()", "list_pop"), ("shout = name.upper()", "text_method"),
            ("parts = line.split(\",\")", "text_split"), ("ok = \"a\" in names", "text_contains"),
            ("r = round(x, 2)", "round_number"), ("big = max(a, b)", "min_max"),
            ("name = input(\"Name? \")", "input_value"), ("x = 5", "assign_variable"), ("print(x)", "print_output"),
            ("import os", "import_module"), ("import numpy as np", "import_as"), ("from math import pi", "import_from"),
            ("break", "break_stmt"), ("continue", "continue_stmt"), ("pass", "pass_stmt"),
            ("assert x > 0, \"positive\"", "assert_stmt"), ("raise ValueError(\"bad\")", "raise_error"),
            ("global counter", "global_stmt"),
        ]
        wrong = []
        for line, want in expect:
            blocks, _m, _r = app.import_code_to_blocks(line + "\n")
            got = blocks[0][0] if blocks else None
            if got != want:
                wrong.append((line, want, got))
        check(f"{len(expect)} typical lines go to the right block {wrong}", not wrong)

        # a whole program: read it, write it back identically, run it
        program = (
            "import random\n"
            "scores = {\"ann\": 3}\n"
            "names = [\"bo\", \"al\"]\n"
            "names.sort()\n"
            "total = 0\n"
            "for i in range(0, 3):\n"
            "    total += i\n"
            "scores[\"bo\"] = total\n"
            "try:\n"
            "    value = scores[\"cy\"]\n"
            "except KeyError:\n"
            "    value = 0\n"
            "finally:\n"
            "    print(\"done\")\n"
            "text = \"-\".join(names)\n"
            "print(text.upper())\n"
            "print(total, value, len(names))\n"
        )
        blocks, matched, raw = app.import_code_to_blocks(program)
        def walk(items):
            for bid_, prm in items:
                yield bid_
                yield from walk(prm.get("_children", []) if isinstance(prm, dict) else [])
        names_used = set(walk(blocks))             # including blocks inside loops and try bodies
        check(f"the program reads back with the new blocks {sorted(names_used)}", {"dict_create", "list_sort", "change_variable", "item_set", "try_block", "except_block", "finally_block", "loop_range", "text_join"} <= names_used)
        regenerated = code_of(app, node, blocks)
        def run(src):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(compile(src, "<p>", "exec"), {})
            return out.getvalue()
        check("the regenerated program prints exactly what the original prints", run(regenerated) == run(program))
        check("the program mostly became real blocks, not raw lines", raw <= 2)
    finally:
        app.destroy()
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
