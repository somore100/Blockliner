"""Scripted UI test (run under Xvfb): every JavaScript and C++ block's code turns back into the same block with its values and body."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI
from ui_common import get_block_attr

FAILURES = []
SKIP = {"raw_code", "node_output", "node_input", "return_statement", "divider", "comment"}


def check(label, cond):
    print(("[OK] " if cond else "[FAIL] ") + label)
    if not cond:
        FAILURES.append(label)


def settle(app):
    for _ in range(3):
        app.update_idletasks()
        app.update()


def code_of(app, node, blocks):
    node["blocks"][:] = blocks
    app.update_generated_code()
    return app.get_clean_code()


WRAPPERS = {"main", "Main", "Program"}


def find_block(blocks, bid):
    """first block with this id anywhere in the tree, ignoring the scaffold's own main/Program wrappers"""
    for b in blocks:
        prm = b[1] if isinstance(b[1], dict) else {}
        if b[0] == bid and prm.get("name") not in WRAPPERS:
            return b
        inner = find_block(prm.get("_children", []), bid)
        if inner is not None:
            return inner
    return None


def run_language(lang):
    app = BlocklinerUI(initial_lang=lang, languages_path="languages")
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
            if lang != "javascript":                # the scaffold wraps the code in main() / a class
                hit = find_block(blocks, bid)
                blocks = [hit] if hit else blocks
            back = [b for b in blocks if b[0] not in ("import_module", "raw_code") or bid in ("import_module", "raw_code")]          # blocks that need a module add its import first
            if not back or back[0][0] != bid:
                bad_id.append((bid, code.strip().replace("\n", " | "), [b[0] for b in blocks][:3]))
                continue
            got = {k: v for k, v in back[0][1].items() if k != "_children"}
            want = {k: v for k, v in params.items() if k != "_children"}
            if got != want:
                bad_params.append((bid, want, got))
            if container and not [c for c in back[0][1].get("_children", []) if c[0] == "print_output"]:
                bad_body.append(bid)
        check(f"[{lang}] all {total} blocks come back as themselves from their own code {bad_id}", not bad_id)
        check(f"[{lang}] ...with their values intact {bad_params}", not bad_params)
        check(f"[{lang}] ...and containers keep their body {bad_body}", not bad_body)

    finally:
        app.destroy()


def main():
    for lang in ("javascript", "cpp", "rust", "go", "java", "csharp", "c"):
        run_language(lang)
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
