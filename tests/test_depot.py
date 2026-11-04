"""Depot: listing, comparing and safely installing extension packages (pure, no Tk)."""
import json, os, stat, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import depot as D

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

def manifest(ext_id="acme/tool", version="1.0.0", api="1.0", **extra):
    return dict({"format": "blockliner-extension", "version": 1, "id": ext_id, "name": "Tool", "extension_version": version,
                 "requires": {"api": api}, "permissions": ["project.read"]}, **extra)

def write_folder(path, m, files=None):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "extension.json"), "w") as f:
        json.dump(m, f)
    for name, text in (files or {}).items():
        os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
        with open(os.path.join(path, name), "w") as f:
            f.write(text)

def write_zip(path, entries, symlink=None):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in entries.items():
            z.writestr(name, text)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")

with tempfile.TemporaryDirectory() as tmp:
    depot = os.path.join(tmp, "depot")
    user = os.path.join(tmp, "extensions")
    os.makedirs(depot)
    write_folder(os.path.join(depot, "tool-folder"), manifest(), {"main.py": "print(1)", "sub/data.txt": "x"})
    write_zip(os.path.join(depot, "zipped.zip"), {"extension.json": json.dumps(manifest("acme/zipped")), "run.py": "pass"})
    write_zip(os.path.join(depot, "nested.zip"), {"nested-1.0/extension.json": json.dumps(manifest("acme/nested")), "nested-1.0/a/b.txt": "b"})
    write_zip(os.path.join(depot, "empty.zip"), {"readme.txt": "no manifest"})
    open(os.path.join(depot, "broken.zip"), "w").write("not a zip")
    open(os.path.join(depot, ".hidden.zip"), "w").write("x")
    open(os.path.join(depot, "notes.txt"), "w").write("ignored")

    pk = {os.path.basename(p["path"]): p for p in D.scan(depot)}
    check("folders and zips are listed, other files ignored", set(pk) == {"tool-folder", "zipped.zip", "nested.zip", "empty.zip", "broken.zip"})
    check("a good package has a manifest", pk["tool-folder"]["manifest"]["id"] == "acme/tool" and pk["zipped.zip"]["kind"] == "zip")
    check("a zip with one top folder is read", pk["nested.zip"]["manifest"]["id"] == "acme/nested")
    check("a package without a manifest says so", pk["empty.zip"]["manifest"] is None and "extension.json" in pk["empty.zip"]["notes"][0])
    check("a damaged zip is reported, not raised", pk["broken.zip"]["manifest"] is None)
    check("a missing depot is an empty list", D.scan(os.path.join(tmp, "nope")) == [])

    # status
    m = pk["tool-folder"]["manifest"]
    check("new when not installed", D.status(m, {}) == "new")
    check("installed when the same version", D.status(m, {"acme/tool": "1.0.0"}) == "installed")
    check("update when the package is newer", D.status(m, {"acme/tool": "0.9.0"}) == "update")
    check("older when the package is older", D.status(m, {"acme/tool": "1.2"}) == "older")
    newer_api = D.X.clean_manifest(manifest(api="9.0"))[0]
    check("incompatible when it needs a newer API", D.status(newer_api, {}) == "incompatible")

    # install: folder
    ok, msg = D.install(pk["tool-folder"], user)
    check("a folder package installs", ok and os.path.isfile(os.path.join(user, "acme-tool", "extension.json"))
          and os.path.isfile(os.path.join(user, "acme-tool", "sub", "data.txt")))
    check("no staging folders are left", not [n for n in os.listdir(user) if n.startswith(".")])
    ok, msg = D.install(pk["tool-folder"], user)
    check("installing again over a name that exists is refused", not ok and "already exists" in msg)
    # update replaces
    import shutil; shutil.rmtree(os.path.join(depot, "tool-folder"))
    write_folder(os.path.join(depot, "tool-folder"), manifest(version="1.1.0"), {"main.py": "print(2)"})
    newer = {os.path.basename(p["path"]): p for p in D.scan(depot)}["tool-folder"]
    ok, msg = D.install(newer, user, existing_folder=os.path.join(user, "acme-tool"))
    check("an update replaces the installed copy", ok and open(os.path.join(user, "acme-tool", "main.py")).read() == "print(2)"
          and not os.path.exists(os.path.join(user, "acme-tool", "sub")))
    check("the old copy is gone", not [n for n in os.listdir(user) if ".old-" in n])
    ok, msg = D.install(newer, user, existing_folder=tmp)
    check("only a subfolder of the extensions folder can be replaced", not ok)

    # install: zips
    ok, _ = D.install(pk["zipped.zip"], user)
    check("a zip with files at the root installs", ok and os.path.isfile(os.path.join(user, "acme-zipped", "run.py")))
    ok, _ = D.install(pk["nested.zip"], user)
    check("a zip with one top folder installs without that folder", ok and os.path.isfile(os.path.join(user, "acme-nested", "a", "b.txt")))
    check("a package without manifest does not install", not D.install(pk["empty.zip"], user)[0])
    check("a damaged package does not install", not D.install(pk["broken.zip"], user)[0])
    ok, msg = D.install({"manifest": newer_api, "path": "x", "kind": "folder", "notes": []}, user)
    check("an incompatible package says why", not ok and "API" in msg)

    # unsafe archives
    for name, entries, symlink in [
            ("climb.zip", {"extension.json": json.dumps(manifest("acme/climb")), "../evil.txt": "x"}, None),
            ("abs.zip", {"extension.json": json.dumps(manifest("acme/abs")), "/tmp/evil.txt": "x"}, None),
            ("link.zip", {"extension.json": json.dumps(manifest("acme/link"))}, "ln")]:
        write_zip(os.path.join(depot, name), entries, symlink)
    bad = {os.path.basename(p["path"]): p for p in D.scan(depot)}
    before = set(os.listdir(user))
    for name in ("climb.zip", "abs.zip", "link.zip"):
        ok, msg = D.install(bad[name], user)
        check(f"{name} is refused", not ok and ("unsafe" in msg or "link" in msg))
    check("refused archives leave nothing behind", set(os.listdir(user)) == before and not os.path.exists(os.path.join(tmp, "evil.txt")))

    # a link inside a folder package
    risky = os.path.join(depot, "risky")
    write_folder(risky, manifest("acme/risky"))
    os.symlink("/etc/passwd", os.path.join(risky, "pw"))
    r = {os.path.basename(p["path"]): p for p in D.scan(depot)}["risky"]
    check("a folder package with a link is refused", not D.install(r, user)[0] and not os.path.exists(os.path.join(user, "acme-risky")))

    # too many files
    big = os.path.join(depot, "big.zip")
    write_zip(big, dict({"extension.json": json.dumps(manifest("acme/big"))}, **{f"f{i}.txt": "x" for i in range(D.MAX_FILES + 5)}))
    b = {os.path.basename(p["path"]): p for p in D.scan(depot)}["big.zip"]
    check("a package with too many files is refused", not D.install(b, user)[0])

    check("folder_name is safe", D.folder_name("Acme/Tool X") == "acme-tool-x" and D.folder_name("../..") == "extension")

print("ALL OK" if not fails else f"FAILURES: {fails}")
