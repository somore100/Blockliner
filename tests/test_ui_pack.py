"""UI builder packs: loading, validation, palette, tree fit. Pure, no Tk."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_pack
from ui_tree import UITree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "ui_packs")
FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))

def base(**kw):
    d = {"format": "blockliner-ui-pack", "version": 1, "id": "python/t", "language": "python",
         "label": "T", "imports": ["import t"], "root_types": ["win"], "run": "{ui}.{root}.go()",
         "function": {"def": "def {fname}():", "indent": "  ", "ret": "return ({pairs})", "pair": "{name}", "call": "{ui} = {fname}()"},
         "layouts": {"grid": {"props": [{"key": "row", "kind": "int", "default": 0}], "code": "{name}.grid({args})"}}}
    d.update(kw); return d

WIN = {"type": "win", "container": True, "code": "{name} = t.Win()", "props": []}
BTN = {"type": "btn", "label": "Button", "category": "Basic",
       "props": [{"key": "text", "kind": "string", "default": "Hi"},
                 {"key": "mode", "kind": "enum", "options": ["a", "b"], "default": "a"}],
       "events": [{"key": "command", "code": "{name}.cfg({handler})"}],
       "code": "{name} = t.Btn({parent}{opts})"}

def main():
    # ---- the shipped tkinter pack
    pack, notes = ui_pack.load_pack(os.path.join(ROOT, "python", "tkinter"))
    check("tkinter pack loads with no notes", pack is not None and notes == [])
    check("tkinter pack has the nine v1 widgets", set(pack.widgets) == {"window", "frame", "label", "button", "checkbutton", "entry", "text", "combobox", "listbox"})
    check("palette follows 'order' and leaves out the window", [c for c, _ in pack.palette()][0] == "Containers" and all(w["type"] != "window" for _c, ws in pack.palette() for w in ws))
    check("containers", pack.is_container("window") and pack.is_container("frame") and not pack.is_container("button") and not pack.is_container("nope"))
    check("defaults only include props that have one", pack.defaults("button") == {"text": "Button", "state": "normal"})
    check("layouts: grid and place", set(pack.layouts) == {"grid", "place"})
    check("window title/geometry are inline props", all(p["inline"] for p in pack.widget("window")["props"]))

    # ---- tree fit
    t = UITree.new("python/tkinter", props={"title": "x"})
    b = t.add(t.root["id"], "button", props={"text": "Go"})
    t.set_event(b, "command", "fn")
    t.set_layout(b, manager="grid", row=0)
    check("a good tree has no problems", pack.tree_problems(t) == [])
    t.add(t.root["id"], "mystery")
    t.set_prop(b, "colour", "red")
    t.set_event(b, "hover", "fn")
    t.set_layout(b, manager="flow")
    t.find(b)["children"].append({"id": "z", "type": "label", "name": "l", "props": {}, "layout": {}, "events": {}, "design": {}, "children": []})
    probs = pack.tree_problems(t)
    check("problems reported: unknown widget/prop/event/manager and leaf with children", len(probs) == 5 and any("mystery" in p for p in probs) and any("colour" in p for p in probs)
          and any("hover" in p for p in probs) and any("flow" in p for p in probs) and any("can't contain" in p for p in probs))
    other = UITree.new("python/other")
    check("wrong pack id is reported", any("not 'python/tkinter'" in p for p in pack.tree_problems(other)))

    # ---- template checking
    f = {"name", "parent", "text"}
    check("good template", ui_pack.template_problems("{name} = X({parent}, {text!r})", f) == [])
    check("unknown placeholder", ui_pack.template_problems("{nope}", f) != [])
    check("bad conversion and format spec", ui_pack.template_problems("{text!a}", f) != [] and ui_pack.template_problems("{text:>5}", f) != [])
    check("unbalanced braces", ui_pack.template_problems("{name", f) != [])
    check("literal text is fine", ui_pack.template_problems("x = 1", f) == [])

    # ---- loading odd packs
    tmp = tempfile.mkdtemp()
    def pk(name, data, widgets=None, scope=""):
        folder = os.path.join(tmp, "python", scope, name)
        write(os.path.join(folder, "pack.json"), data)
        for fn, w in (widgets or {}).items():
            write(os.path.join(folder, "widgets", fn), w)
        return folder
    good = pk("good", base(widgets=[WIN]), {"btn.json": BTN})
    p, n = ui_pack.load_pack(good)
    check("inline + file widgets both load", p is not None and set(p.widgets) == {"win", "btn"} and n == [])
    check("prop defaults normalised", p.widget("btn")["props"][0]["arg"] == "text" and p.widget("btn")["props"][0]["optional"] is False)
    check("a list file holds several widgets", ui_pack.load_pack(pk("multi", base(id="python/multi", widgets=[WIN]), {"all.json": [BTN, dict(BTN, type="btn2")]}))[0].widgets.keys() >= {"btn", "btn2"})

    p, n = ui_pack.load_pack(pk("badw", base(id="python/badw", widgets=[WIN]), {
        "a.json": dict(BTN, code="{oops}"), "b.json": dict(BTN, type="Bad Type"),
        "c.json": {"type": "nocode"}, "d.json": "not json{", "e.json": 5,
        "f.json": dict(BTN, props=[{"key": "x", "kind": "weird"}, {"key": "name", "kind": "string"},
                                   {"key": "m", "kind": "enum"}, {"key": "i", "kind": "int", "default": "no"}]),
        "g.json": dict(BTN, type="ok_btn", events=[{"key": "e", "code": "{bad}"}, {"nokey": 1}])}))
    check("bad widgets are skipped with notes, the rest load", p is not None and set(p.widgets) == {"win", "btn", "ok_btn"} and len(n) >= 8)
    check("a widget with bad props loses them, bad events too, and still loads", p.widget("btn")["props"] == [] and p.widget("ok_btn")["events"] == [])
    p, n = ui_pack.load_pack(pk("dup", base(id="python/dup", widgets=[WIN, dict(WIN, code="other")])))
    check("duplicate widget type keeps the first", p.widget("win")["code"] == ["{name} = t.Win()"] and any("twice" in x for x in n))
    p, n = ui_pack.load_pack(pk("raw", base(id="python/raw", widgets=[WIN, {"type": "r", "code_raw": "anything {goes}"}])))
    check("code_raw is taken as is", p.widget("r")["code_raw"] == "anything {goes}" and p.widget("r")["code"] is None)
    p, n = ui_pack.load_pack(pk("lay", base(id="python/lay", widgets=[WIN], layouts={"grid": {"code": "{x}"}, "ok": {"code": "{name}.ok()"}, "Bad Name": {}})))
    check("bad layouts are dropped, good ones kept", set(p.layouts) == {"ok"} and len(n) == 2)

    for label, data in (("not a pack", {"format": "nope"}), ("future version", base(version=9)),
                        ("id/language mismatch", base(id="rust/t")), ("bad id", base(id="python/Bad Name")),
                        ("empty root_types", base(root_types=[])), ("imports not a list", base(imports="x")),
                        ("root type missing", base(root_types=["ghost"], widgets=[WIN])),
                        ("no function wrapper", {k: v for k, v in base(widgets=[WIN]).items() if k != "function"}),
                        ("bad function template", base(function={"def": "{nope}", "indent": " ", "ret": "r", "pair": "p", "call": "c"})),
                        ("unknown quote style", base(quote="klingon")),
                        ("bad run placeholder", base(run="{parent}"))):
        pdata, pn = ui_pack.load_pack(pk("x_" + label.replace(" ", "_").replace("/", "_"), data))
        check(f"rejected: {label}", pdata is None and pn)
    check("missing folder and broken json don't raise", ui_pack.load_pack(os.path.join(tmp, "none")) [0] is None
          and ui_pack.load_pack(pk("brk", "{{{"))[0] is None)

    # ---- finding packs
    root = tempfile.mkdtemp()
    def put(rel, data): write(os.path.join(root, *rel), data)
    put(["python", "alpha", "pack.json"], base(id="python/alpha", widgets=[WIN]))
    put(["python", "beta", "pack.json"], base(id="python/beta", widgets=[WIN]))
    put(["python", "custom", "mine", "pack.json"], base(id="python/mine", widgets=[WIN]))
    put(["python", "custom", "dupe", "pack.json"], base(id="python/alpha", widgets=[WIN]))
    put(["python", ".hidden", "pack.json"], base(id="python/hidden", widgets=[WIN]))
    put(["rust", "rs", "pack.json"], base(id="rust/rs", language="rust", widgets=[WIN]))
    put(["python", "broken", "pack.json"], "nope")
    found, notes = ui_pack.find_packs([root, root], "python")
    check("python packs: prebuilt then custom, sorted, deduped, hidden/other-language ignored",
          [(p.id, p.scope) for p in found] == [("python/alpha", "prebuilt"), ("python/beta", "prebuilt"), ("python/mine", "custom")])
    check("duplicate id and broken pack are reported", any("already loaded" in n for n in notes) and any("broken" in n for n in notes))
    check("other language sees only its own", [p.id for p in ui_pack.find_packs([root], "rust")[0]] == ["rust/rs"])
    check("unsafe language loads nothing", ui_pack.find_packs([root], "../x") == ([], []) and ui_pack.find_packs([root], None) == ([], []))
    check("missing root is fine", ui_pack.find_packs([os.path.join(root, "nope")], "python") == ([], []))
    check("the real ui_packs folder finds tkinter", [p.id for p in ui_pack.find_packs([ROOT], "python")[0]] == ["python/tkinter"])

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
