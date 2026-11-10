"""Pure checks for the audit round: export helpers, new-language scaffold,
project ids, metadata in any comment style, extension consent."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import export_helpers as E
import language_scaffold as LS
import portable
import project_file as PF
import extensions as X
from engine.loader import load_language_pack
from nodes_model import make_node

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    exts = {".py": "python", ".cpp": "cpp", ".go": "go", ".java": "java", ".html": "html", ".c": "c"}
    check("every language gets its own file ending", [E.file_ending(l, exts) for l in ("python", "go", "java", "html", "c")] == [".py", ".go", ".java", ".html", ".c"])
    check("a language with no ending falls back to .txt", E.file_ending("lua", exts) == ".txt")
    check("comment lines use the pack's token", E.comment_line("//", "hi") == "// hi" and E.comment_line("#", "hi") == "# hi" and E.comment_line(None, "hi") == "# hi")
    check("html comments are closed", E.comment_line("<!--", "hi") == "<!-- hi -->")
    head = E.header("//", "go", ["Project blocks: 3"])
    check("a go header never starts with #", all(l.startswith("//") for l in head.strip().split("\n")) and head.endswith("\n\n"))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "x.txt")
        E.write_text(p, "arrow → and é")
        with open(p, encoding="utf-8") as f:
            check("export text is written as UTF-8", f.read() == "arrow → and é")
        one, two = E.private_folder(), E.private_folder()
        check("private folders are new and different", os.path.isdir(one) and one != two and (os.stat(one).st_mode & 0o077) == 0)
        os.rmdir(one); os.rmdir(two)

        # a new language is a real pack
        check("bad language names are explained", LS.name_problem("") != "" and LS.name_problem("My Lang") != "" and LS.name_problem("../x") != "" and LS.name_problem("lua") == "")
        folder = LS.write_starter(d, "lua", "--")
        manifest, blocks = load_language_pack(folder)
        check("the new pack loads with its comment token", manifest is not None and manifest["comment_token"] == "--")
        check("the new pack has the Raw Code block", blocks is not None and "raw_code" in blocks)
        try:
            LS.write_starter(d, "lua"); again = False
        except FileExistsError:
            again = True
        check("an existing language is never overwritten", again)
        try:
            LS.write_starter(d, "Bad Name"); bad = False
        except ValueError:
            bad = True
        check("a bad name makes no folder", bad and not os.path.exists(os.path.join(d, "Bad Name")))

        # metadata round-trips for any comment token
        n = make_node("a", node_id="a", blocks=[], order=1)
        meta = portable.build_metadata([n], "lua", "a")
        for tok in ("#", "//", "--", ["<!--", "-->"], ";", "%"):
            body = portable.render_meta_block(meta, tok)
            text = "x = 1\n\n" + body
            _nodes, got, diag = portable.parse_portable(text)
            check(f"metadata survives comment style {tok!r}", got is not None and got.get("language") == "lua")

        # node ids
        raw = {"nodes": [{"name": "A b", "id": "has space", "blocks": []},
                         {"name": "B", "id": "x\nimport os  # injected", "blocks": []},
                         {"name": "C", "id": "fine-id_1", "blocks": []},
                         {"name": "D", "id": "fine-id_1", "blocks": []}]}
        lang, nodes, active, notes = PF.parse_project_data({"format": "blockliner-project", "version": 2, "language": "python", **raw}, ["python"])
        ids = [x["id"] for x in nodes]
        check("every loaded node id is safe for marker lines", all(portable.NODE_MARKER_RE.fullmatch(f"$$$blockliner:node:{i}$$$ start") for i in ids))
        check("a good id is kept and a duplicate renamed", ids[2] == "fine-id_1" and len(set(ids)) == 4)
        files, idx, notes = PF.parse_workspace_data({"format": "blockliner-project", "version": 3, "type": "codebuilder",
                                                      "files": [["not", "a", "file"], {"language": "python", "nodes": [{"name": "m", "id": "m1", "blocks": []}]}]}, ["python"])
        check("a list in place of a file is skipped, not a crash", len(files) == 1 and any("damaged" in x for x in notes))

        # consent
        ext = {"format": "blockliner-extension", "version": 1, "id": "me/auto", "name": "Auto", "requires": {"api": "1.0"},
               "permissions": ["project.write"], "enabled_by_default": True, "run": {"command": ["python3", "x.py"]}}
        for scope in ("built-in", "user"):
            root = os.path.join(d, scope); os.makedirs(os.path.join(root, "e"))
            with open(os.path.join(root, "e", "extension.json"), "w") as f:
                json.dump(ext, f)
        for scope, want in (("built-in", True), ("user", False)):
            found = X.find_extensions([(os.path.join(d, scope), scope)])
            check(f"enabled_by_default is {'honoured' if want else 'ignored'} for {scope}", X.is_enabled(found[0]["manifest"], {}) is want)

    print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__":
    main()
