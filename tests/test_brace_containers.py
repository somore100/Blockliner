"""
Scripted UI test (run under Xvfb): brace-style containers (JS, C, C++,
C#, Java, Rust, Go) parse into real nested blocks, driven by braces
rather than indentation. Anything that isn't a clean container must
fall back to verbatim raw code - never crash, hang, or lose text.

Not a pytest file - run directly, same convention as the other tests.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import BlocklinerUI

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


TREE = [
    ("func_def", {"name": "f", "params": "a", "_children": [
        ("assign_variable", {"variable": "y", "value": "2"}),
        ("if_statement", {"condition": "y > 1", "_children": [
            ("print_output", {"value": "y"}),
            ("loop_while", {"condition": "y < 5", "_children": [
                ("assign_variable", {"variable": "y", "value": "y + 1"})]})]})]}),
    ("print_output", {"value": "1"}),
]

BRACE_LANGS = ["javascript", "c", "cpp", "csharp", "java", "rust", "go"]


def render(app, blocks, lang):
    return "".join(app.render_block_list(blocks, lang))


def strip_ws(text):
    return "".join(text.split())


def main():
    # --- Every brace language: render a nested tree, parse it back,
    # re-render: identical text and not a single raw line. ---
    for lang in BRACE_LANGS:
        app = BlocklinerUI(initial_lang=lang, languages_path="languages")
        app.update()
        code = render(app, TREE, lang)
        blocks, matched, raw = app.import_code_to_blocks(code)
        check(f"{lang}: nested tree round-trips byte-identically",
              render(app, blocks, lang) == code)
        check(f"{lang}: no raw fallback needed (matched={matched}, raw={raw})", raw == 0)
        check(f"{lang}: top level is func_def + print",
              [b[0] for b in blocks] == ["func_def", "print_output"])
        app.destroy()

    # --- if / else if / else chain, every brace language, at top level
    # and nested; plus the exact else style each language must emit. ---
    chain = [
        ("if_statement", {"condition": "a == 1", "_children": [("print_output", {"value": "1"})]}),
        ("elif_statement", {"condition": "a == 2", "_children": [("print_output", {"value": "2"})]}),
        ("else_statement", {"_children": [("print_output", {"value": "3"})]}),
        ("print_output", {"value": "4"}),
    ]
    for lang in BRACE_LANGS:
        app = BlocklinerUI(initial_lang=lang, languages_path="languages")
        app.update()
        for label, tree in (("top-level", chain),
                            ("nested", [("func_def", {"name": "f", "params": "a", "_children": chain})])):
            code = render(app, tree, lang)
            blocks, _m, raw = app.import_code_to_blocks(code)
            check(f"{lang}: if/else-if/else chain ({label}) round-trips, 0 raw",
                  render(app, blocks, lang) == code and raw == 0)
        code = render(app, chain, lang)
        if lang == "csharp":
            check("csharp: Allman else stays on its own line (no '} else')",
                  "\nelse\n{" in code and "} else" not in code)
        else:
            check(f"{lang}: else joined onto the closing brace ('}} else')",
                  "} else if " in code and "} else {" in code)
        app.destroy()

    # --- Adversarial cases, on JavaScript (K&R) ---
    app = BlocklinerUI(initial_lang="javascript", languages_path="languages")
    app.update()

    def parse(code):
        blocks, _m, _r = app.import_code_to_blocks(code)
        return blocks, render(app, blocks, "javascript")

    src = "if (x) {\n    a();\n} else {\n    b();\n}\n"
    blocks, out = parse(src)
    check("'} else {' now parses to if_statement + else_statement, byte-identical",
          [b[0] for b in blocks] == ["if_statement", "else_statement"] and out == src)

    src = "if (a) {\n    x();\n} else if (b) {\n    y();\n} else {\n    z();\n}\n"
    blocks, out = parse(src)
    check("'} else if (b) {' chain parses to if/elif/else and round-trips",
          [b[0] for b in blocks] == ["if_statement", "elif_statement", "else_statement"]
          and blocks[1][1]["condition"] == "b" and out == src)

    src = "if (x) {\n    a();\n}\nelse {\n    b();\n}\n"
    blocks, out = parse(src)
    check("'else' on its own line is accepted and normalized to '} else {'",
          [b[0] for b in blocks] == ["if_statement", "else_statement"]
          and out == "if (x) {\n    a();\n} else {\n    b();\n}\n")

    src = "if (x) {\n    a();\n} else {\n    b();\n"
    blocks, out = parse(src)
    check("else body left unclosed (mid-typing): falls back safely, no code lost",
          blocks[0][0] == "if_statement" and strip_ws(out) == strip_ws(src))

    blocks, out = parse("else {\n    b();\n}\n")
    check("a stray else with no preceding if is kept as its own block, text preserved",
          [b[0] for b in blocks] == ["else_statement"] and out == "else {\n    b();\n}\n")

    src = 'if (x) {\n    s = "}";\n}\n'
    blocks, out = parse(src)
    check("a brace inside a string literal does not end the body early",
          [b[0] for b in blocks] == ["if_statement"] and out == src)

    src = "if (x) {\n    a();\n"
    blocks, out = parse(src)
    check("unclosed body (mid-typing): header stays raw, no hang, no code lost",
          blocks[0][0] == "raw_code" and strip_ws(out) == strip_ws(src))

    src = "if (x) {\n    a();\n}\n}\n"
    blocks, out = parse(src)
    check("stray extra closing brace is kept, container still found",
          [b[0] for b in blocks][0] == "if_statement" and out == src)

    blocks, out = parse("if (x) {\nfoo();\n}\n")
    check("unindented body is recognized and re-indented canonically",
          [b[0] for b in blocks] == ["if_statement"] and out == "if (x) {\n    foo();\n}\n")

    blocks, _out = parse("if (x) {\n}\n")
    check("empty body becomes an empty container",
          blocks[0][0] == "if_statement" and blocks[0][1]["_children"] == [])

    src = "if (a) {\n    switch (x) {\n        case 1: break;\n    }\n}\n"
    blocks, out = parse(src)
    check("nested unmatched braces inside a body are balanced correctly",
          [b[0] for b in blocks] == ["if_statement"]
          and len(blocks[0][1]["_children"]) == 3
          and strip_ws(out) == strip_ws(src))

    blocks, out = parse("let x = 5;\n    let y = 6;\n")
    check("indented top-level lines still match real blocks (indent is cosmetic here)",
          [b[0] for b in blocks] == ["assign_variable", "assign_variable"]
          and out == "let x = 5;\nlet y = 6;\n")

    src = "if (a) {\n    b();\n}\nif (c) {\n    d();\n}\n"
    blocks, out = parse(src)
    check("back-to-back sibling containers both found",
          [b[0] for b in blocks] == ["if_statement", "if_statement"] and out == src)

    app.destroy()

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll brace-container assertions passed.")


if __name__ == "__main__":
    main()
