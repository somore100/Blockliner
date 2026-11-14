"""Every language pack's block files are well formed (pure): known keys, template placeholders that name real
params, defaults, dropdown defaults that are in their list, no two blocks with the same name, containers with a body."""
import glob, json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from engine.loader import load_language_pack

FAILURES = []
def check(label, cond):
    if not cond:
        print(f"[FAIL] {label}")
        FAILURES.append(label)

KNOWN_CATEGORIES = {"Basic", "Math", "Control", "Functions", "Data Structures", "String Operations", "Modules", "GUI", "Nodes", "Advanced"}
PH = re.compile(r"\[\[(\w+)\]\]")

def main():
    packs = sorted(d for d in glob.glob(os.path.join(ROOT, "languages", "*")) if os.path.isdir(d))
    total = 0
    for pack in packs:
        lang = os.path.basename(pack)
        manifest, blocks = load_language_pack(pack)
        check(f"{lang}: the pack loads", manifest is not None and blocks)
        files = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(pack, "blocks", "*.json"))}
        check(f"{lang}: no block file was dropped by validation", files == set(blocks or {}))
        names = {}
        for bid, d in (blocks or {}).items():
            total += 1
            where = f"{lang}/{bid}"
            params = d.get("params", [])
            pnames = [p.get("name") for p in params]
            check(f"{where}: has a display name, category and template", all(isinstance(d.get(k), str) and d.get(k) for k in ("display_name", "category", "template")))
            check(f"{where}: param names are unique", len(pnames) == len(set(pnames)))
            used = set(PH.findall(d.get("template", "")))
            check(f"{where}: template placeholders are params (or body)", used - set(pnames) - {"body"} == set())
            if d.get("style") != "divider":          # a divider's colour is drawn, not written into the code
                check(f"{where}: every param is used in the template", set(pnames) - used == set())
            for p in params:
                check(f"{where}.{p.get('name')}: has a type and a default", isinstance(p.get("type"), str) and "default" in p)
                ch = p.get("choices")
                if isinstance(ch, list):
                    check(f"{where}.{p['name']}: default is one of the choices", p.get("default") in ch)
                    check(f"{where}.{p['name']}: choices are all text", all(isinstance(c, str) and c for c in ch))
            if d.get("is_container"):
                check(f"{where}: a container has a [[body]]", "[[body]]" in d["template"])
            else:
                check(f"{where}: a non-container has no [[body]]", "[[body]]" not in d["template"])
            if "requires" in d:
                check(f"{where}: requires is a list of names", isinstance(d["requires"], list) and all(isinstance(r, str) for r in d["requires"]))
            key = (d.get("display_name") or "").strip().lower()
            check(f"{where}: display name '{d.get('display_name')}' already used by {names.get(key)}", key not in names)
            names[key] = bid
            if lang == "python":
                check(f"{where}: category '{d.get('category')}' has a palette colour", d.get("category") in KNOWN_CATEGORIES)
    print(f"checked {total} blocks in {len(packs)} packs")
    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
