"""UI builder widget tree: pure model, no Tk, runs anywhere."""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ui_tree
from ui_tree import UITree, ReadOnlyError

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def raises(exc, fn, *a, **kw):
    try: fn(*a, **kw)
    except exc: return True
    except Exception: return False
    return False

def counter():
    n = [0]
    def f():
        n[0] += 1
        return f"w{n[0]}"
    return f

def main():
    t = UITree.new("python/tkinter", is_container=lambda ty: ty in ("window", "frame"), id_factory=counter())
    root = t.root["id"]
    check("new tree has a window root named root", t.root["type"] == "window" and t.root["name"] == "root")

    # ---- add / names
    b1 = t.add(root, "button")
    b2 = t.add(root, "button")
    check("names are uniquified", [t.find(b1)["name"], t.find(b2)["name"]] == ["button", "button_2"])
    check("explicit invalid name falls back to a valid one", t.find(t.add(root, "label", name="for"))["name"] == "widget")
    f = t.add(root, "frame", index=0)
    check("index inserts at that position", t.root["children"][0]["id"] == f)
    check("leaf widgets can't hold children", raises(ValueError, t.add, b1, "label"))
    check("unknown parent raises KeyError", raises(KeyError, t.add, "nope", "label"))
    check("find / parent_of", t.find(b1)["type"] == "button" and t.parent_of(b1)["id"] == root and t.parent_of(root) is None)

    # ---- move
    t.move(b1, f)
    check("move reparents", t.parent_of(b1)["id"] == f)
    inner_f = t.add(f, "frame")
    check("can't move into own subtree", raises(ValueError, t.move, f, inner_f))
    check("can't move a widget into itself", raises(ValueError, t.move, f, f))
    check("root can't move or be removed", raises(ValueError, t.move, root, f) and raises(ValueError, t.remove, root))
    t.move(b1, root, index=0)
    check("move to index", t.root["children"][0]["id"] == b1)

    # ---- props / layout / events / rename
    t.set_prop(b1, "text", "Save")
    t.set_layout(b1, manager="grid", row=0, column=1)
    t.set_event(b1, "command", "fn1")
    node = t.find(b1)
    check("props/layout/events stored", node["props"]["text"] == "Save" and node["layout"]["column"] == 1 and node["events"]["command"] == "fn1")
    t.set_event(b1, "command", None)
    check("event can be unlinked", "command" not in t.find(b1)["events"])
    check("rename to a taken name gets a suffix", t.rename(b2, "button") == "button_2")
    check("rename to a free name is used as is", t.rename(b2, "btn_cancel") == "btn_cancel" and t.find(b2)["name"] == "btn_cancel")
    check("invalid rename raises", raises(ValueError, t.rename, b2, "1bad") and raises(ValueError, t.rename, b2, "class"))
    check("renaming to own name is a no-op", t.rename(b1, t.find(b1)["name"]) == t.find(b1)["name"])

    # ---- remove / duplicate
    t.remove(f)
    check("remove drops the subtree", t.find(f) is None)
    t2 = UITree.new("p", id_factory=counter())
    r2 = t2.root["id"]
    fr = t2.add(r2, "frame", name="box")
    inner = t2.add(fr, "button", name="ok")
    t2.set_event(inner, "command", "fn")
    dup = t2.duplicate(fr)
    ids = [n["id"] for n in t2.walk()]
    names = [n["name"] for n in t2.walk()]
    check("duplicate gives fresh ids and unique names", len(ids) == len(set(ids)) == 5 and len(names) == len(set(names)))
    check("duplicate lands right after the original", t2.root["children"][1]["id"] == dup)
    check("duplicate keeps event links", t2.find(dup)["children"][0]["events"]["command"] == "fn")
    check("root can't be duplicated", raises(ValueError, t2.duplicate, r2))

    # ---- undo / redo
    t3 = UITree.new("p", id_factory=counter())
    r3 = t3.root["id"]
    check("nothing to undo at the start", not t3.can_undo and t3.undo() is False)
    a = t3.add(r3, "label")
    t3.set_prop(a, "text", "H"); t3.set_prop(a, "text", "He"); t3.set_prop(a, "text", "Hel")
    check("typing in one field is one undo step", len(t3._undo) == 2)
    t3.undo()
    check("undo restores before the typing", "text" not in t3.find(a)["props"])
    t3.undo()
    check("undo again removes the add", t3.find(a) is None)
    check("redo re-applies", t3.redo() and t3.find(a) is not None and "text" not in t3.find(a)["props"])
    t3.redo()
    check("redo again re-applies the typing", t3.find(a)["props"]["text"] == "Hel")
    t3.undo(); t3.set_prop(a, "text", "x")
    check("a new edit clears redo", not t3.can_redo)
    t3.set_prop(a, "text", "y"); t3.set_prop(a, "other", "z")
    check("different fields are different steps", len(t3._undo) >= 3)
    t4 = UITree.new("p", id_factory=counter())
    for i in range(ui_tree.MAX_UNDO + 20):
        t4.add(t4.root["id"], "label")
    check("undo history is bounded", len(t4._undo) == ui_tree.MAX_UNDO)

    # ---- save / load
    doc = t.to_dict()
    check("document header", doc["format"] == "blockliner-ui" and doc["version"] == 1 and doc["pack"] == "python/tkinter")
    back = UITree.from_dict(json.loads(json.dumps(doc)))
    check("round trip is identical", back.to_dict() == doc and not back.read_only)
    doc2 = copy.deepcopy(doc)
    doc2["future_key"] = {"a": 1}
    doc2["root"]["children"][0]["mystery"] = [1, 2]
    doc2["root"]["children"][0]["type"] = "pack_not_installed_widget"
    back2 = UITree.from_dict(doc2)
    check("unknown keys and widget types survive", back2.to_dict()["future_key"] == {"a": 1}
          and back2.to_dict()["root"]["children"][0]["mystery"] == [1, 2]
          and back2.to_dict()["root"]["children"][0]["type"] == "pack_not_installed_widget")
    newer = copy.deepcopy(doc); newer["version"] = 99
    ro = UITree.from_dict(newer)
    check("newer version loads read-only", ro.read_only and raises(ReadOnlyError, ro.add, ro.root["id"], "label"))
    check("read-only tree keeps its version on save", ro.to_dict()["version"] == 99)
    check("read-only can't undo/redo", ro.undo() is False and ro.redo() is False)
    for label, bad in (("not a dict", 5), ("wrong format", {"format": "x", "version": 1}),
                       ("bad version", {"format": "blockliner-ui", "version": 0, "root": {}}),
                       ("no root", {"format": "blockliner-ui", "version": 1}),
                       ("widget without id", {"format": "blockliner-ui", "version": 1, "root": {"type": "window"}}),
                       ("duplicate ids", {"format": "blockliner-ui", "version": 1, "root": {"id": "a", "type": "window", "children": [{"id": "a", "type": "x"}]}}),
                       ("bad children", {"format": "blockliner-ui", "version": 1, "root": {"id": "a", "type": "window", "children": 3}})):
        check(f"damaged document refused: {label}", raises(ValueError, UITree.from_dict, bad))
    lean = UITree.from_dict({"format": "blockliner-ui", "version": 1, "pack": "p", "root": {"id": "a", "type": "window"}})
    check("missing optional fields are filled in", lean.root["props"] == {} and lean.root["children"] == [] and lean.root["name"] == "window")
    check("to_dict does not alias the live tree", copy.deepcopy(t.to_dict()) == t.to_dict() and t.to_dict()["root"] is not t.root)

    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
