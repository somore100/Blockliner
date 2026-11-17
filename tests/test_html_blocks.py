"""The HTML block pack: every block loads, renders with its defaults, and the tags it opens are closed."""
import os
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.loader import load_language_pack
from engine.renderer import render_block

FAILURES = []
VOID = {"br", "hr", "img", "input", "meta", "link"}


def check(label, cond):
    print(("[OK] " if cond else "[FAIL] ") + label)
    if not cond:
        FAILURES.append(label)


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], False

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.bad = True


def main():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "languages", "html")
    manifest, blocks = load_language_pack(root)
    check("the pack loads", manifest is not None and len(blocks) >= 45)
    bad = []
    for bid, b in blocks.items():
        if bid == "raw_code":
            continue
        params = {p["name"]: p.get("default", "") for p in b.get("params", [])}
        try:
            code = render_block(b, params, ["<p>x</p>"] if b.get("is_container") else None, blocks)
        except Exception as e:
            bad.append(f"{bid}: {e}")
            continue
        parser = Balance()
        parser.feed(code)
        if parser.bad or parser.stack or "[[" in code:
            bad.append(f"{bid}: {code!r}")
    check("every block renders balanced html" + (f" - {bad}" if bad else ""), not bad)
    for p in blocks["input"]["params"]:
        if p["name"] == "type":
            check("input offers choices", "checkbox" in p["choices"])
    check("categories are grouped", {"Layout", "Text", "Lists", "Table", "Forms", "Media", "Head"} <= {b.get("category") for b in blocks.values()})
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
