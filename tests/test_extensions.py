"""Extensions: manifests, compatibility, what is on, layout, built-ins (pure, no Tk)."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import extensions as X
import extensions_builtin as B

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

GOOD = {"format": "blockliner-extension", "version": 1, "id": "me/demo", "name": "Demo", "requires": {"api": "1.0"},
        "permissions": ["ui.panel", "bogus"], "panel": {"title": "P", "dock": "left", "width": 300}}

def write(root, name, data, raw=None):
    os.makedirs(os.path.join(root, name))
    with open(os.path.join(root, name, "extension.json"), "w") as f:
        f.write(raw if raw is not None else json.dumps(data))

def main():
    check("versions parse", X.parse_version("1.2") == (1, 2) and X.parse_version("1") == (1, 0) and X.parse_version("x") is None and X.parse_version(None) is None)
    m, notes = X.clean_manifest(GOOD)
    check("a good manifest is read, an unknown permission is noted", m["id"] == "me/demo" and m["permissions"] == ["ui.panel"] and len(notes) == 1)
    check("panel settings are cleaned", m["panel"] == {"title": "P", "dock": "left", "width": 300} and m["pin"] is True)
    check("a command-only extension is not pinned", X.clean_manifest({**GOOD, "panel": None, "menus": [{"label": "Go", "command": "go"}]})[0]["pin"] is False)
    check("pin can be asked for", X.clean_manifest({**GOOD, "pin": False})[0]["pin"] is False)
    for label, bad in (("wrong format", {**GOOD, "format": "x"}), ("bad id", {**GOOD, "id": "Demo"}), ("no name", {**GOOD, "name": ""}),
                       ("bad api", {**GOOD, "requires": {"api": "abc"}}), ("future manifest", {**GOOD, "version": 9}), ("not an object", [])):
        check(f"damaged manifest is refused: {label}", X.clean_manifest(bad)[0] is None)

    with tempfile.TemporaryDirectory() as d:
        write(d, "a", GOOD)
        write(d, "b", None, raw="{nope")
        write(d, "c", {**GOOD, "id": "me/other", "builtin": "statistics"})
        write(d, "dup", GOOD)
        found = X.find_extensions([(d, "user")])
        ids = [e["manifest"]["id"] for e in found if e["manifest"]]
        check("good ones load, a broken one is a note, duplicates are dropped", ids == ["me/demo", "me/other"] and sum(1 for e in found if not e["manifest"]) == 1)
        check("only shipped extensions may use built-in code", all(e["manifest"]["builtin"] == "" for e in found if e["manifest"]))
        check("a missing folder is fine", X.find_extensions([("/nonexistent", "user")]) == [])

    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extensions", "builtin")
    shipped = X.find_extensions([(root, "built-in")])
    check("the two shipped extensions load cleanly", {e["manifest"]["id"] for e in shipped if e["manifest"]} == {"blockliner/statistics", "blockliner/copy-code"}
          and all(not e["notes"] for e in shipped))

    check("compatible", X.compatibility(X.clean_manifest(GOOD)[0])[0] == "ok")
    newer = X.clean_manifest({**GOOD, "requires": {"api": "1.5"}})[0]
    check("needs a newer Blockliner", X.compatibility(newer)[0] == "newer_needed" and "Update Blockliner" in X.compatibility(newer)[1])
    older = X.clean_manifest({**GOOD, "requires": {"api": "1.0"}})[0]
    check("an older major is refused", X.compatibility(older, api=(2, 0))[0] == "older_api" and X.compatibility(older, api=(2, 0))[1])
    check("a newer minor than needed is fine", X.compatibility(older, api=(1, 7))[0] == "ok")

    stats = next(e for e in shipped if e["manifest"]["id"] == "blockliner/statistics")["manifest"]
    check("default comes from the manifest, the user's choice wins", X.is_enabled(stats, {}) is True
          and X.is_enabled(stats, {"extensions_enabled": {"blockliner/statistics": False}}) is False)
    s = {}
    X.set_enabled(s, "me/demo", True)
    check("set_enabled stores it", s == {"extensions_enabled": {"me/demo": True}})
    check("junk settings don't break it", X.is_enabled(stats, {"extensions_enabled": "x"}) is True)
    check("safe start by setting or environment", X.safe_start({"extensions_safe_start": True}, {}) and X.safe_start({}, {"BLOCKLINER_SAFE": "1"}) and not X.safe_start({}, {}))
    on = X.active(shipped, {}, {})
    check("shipped extensions are active by default", len(on) == 2)
    check("nothing is active in safe start", X.active(shipped, {}, {"BLOCKLINER_SAFE": "1"}) == [])
    check("a disabled one is not active", [e["manifest"]["id"] for e in X.active(shipped, {"extensions_enabled": {"blockliner/statistics": False}}, {})] == ["blockliner/copy-code"])
    lay = X.layout(on)
    check("the panel goes in the bar, the command in the menu", [e["manifest"]["id"] for e in lay["pinned"]] == ["blockliner/statistics"]
          and lay["commands"][0][1]["label"] == "Copy generated code" and lay["overflow_panels"] == [])
    many = [{"manifest": X.clean_manifest({**GOOD, "id": f"me/p{i}"})[0]} for i in range(5)]
    lay = X.layout(many)
    check("only a few icons are pinned, the rest overflow", len(lay["pinned"]) == X.MAX_PINNED and len(lay["overflow_panels"]) == 2)

    files = [{"language": "python", "imports": ["time", 5], "nodes": [
                {"kind": "function", "blocks": [["print", {}], ["if", {"_children": [["print", {}], ["print", {}]]}]],
                 "child_nodes": []},
                {"kind": "class", "child_nodes": [{"kind": "function", "blocks": [["x", {}]]}]}]},
             {"language": "c", "nodes": []}]
    st = B.project_stats(files)
    check("statistics count files, nodes, nested blocks and imports", st == {"files": 2, "nodes": 2, "blocks": 5, "imports": 1, "languages": {"python": 1, "c": 1}})
    desc = B.statistics_panel(files)
    check("the panel is a column with a refresh button", desc["type"] == "column" and desc["children"][-1] == {"type": "button", "text": "Refresh", "command": "refresh"})
    check("copy command returns the code and a message", B.run_command("copy_code", "copy", {"code": "a\n\nb\n"}) == {"clipboard": "a\n\nb\n", "notify": "Copied 2 lines of code."})
    check("an unknown command does nothing", B.run_command("copy_code", "zzz", {}) == {})
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
