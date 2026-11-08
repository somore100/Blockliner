"""Pure test: the Divider block exists in every language and writes a comment line."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import loader
from engine.renderer import with_generate_code

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "languages")
for lang in sorted(os.listdir(root)):
    if not os.path.isdir(os.path.join(root, lang, "blocks")):
        continue
    blocks = with_generate_code(loader.load_language_pack(os.path.join(root, lang))[1])
    d = blocks.get("divider")
    check(f"{lang}: has a divider block", d is not None)
    if d is None:
        continue
    code = d["generate_code"]({"title": "Setup", "color": "blue"}, [], lang)
    check(f"{lang}: writes one comment line with the title", "Setup" in code and code.count("\n") == 1)
    names = [p["name"] for p in d["params"]]
    check(f"{lang}: asks for a title and a colour", names == ["title", "color"])

from divider import DIVIDER_COLORS
choices = json.load(open(os.path.join(root, "python", "blocks", "divider.json")))["params"][1]["choices"]
check("every colour offered has a line colour", all(c in DIVIDER_COLORS for c in choices))
print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
sys.exit(1 if FAILURES else 0)
