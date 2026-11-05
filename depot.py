"""The depot: a folder of extension packages you can install from (pure, no Tk).

A package is a folder or a .zip holding an extension.json (at its root, or inside
one top-level folder). Nothing here runs the package or reaches the internet:
scan() lists what is in the folder, status() compares it with what is installed,
and install() copies it into the user's extensions folder, refusing anything
unsafe (paths that climb out, links, huge archives). A new install stays off
until the user turns it on and agrees to its permissions.
"""
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile

import extensions as X

MAX_FILES = 500
MAX_BYTES = 50 * 1024 * 1024
PACKAGE_SUFFIXES = (".zip", ".blx")


def _ver(text):
    v = X.parse_version(text) if isinstance(text, str) else None
    return tuple((list(v) + [0, 0, 0])[:3]) if v else (0, 0, 0)


def _read_manifest(raw_bytes, where):
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return None, [f"{where} could not be read ({e})"]
    return X.clean_manifest(raw, where)


# ---- listing ---------------------------------------------------------------------
def scan(depot_dir):
    """[{"manifest", "path", "kind", "notes"}] for every package in the folder.
    A broken package has manifest None and says why in notes."""
    out = []
    if not os.path.isdir(depot_dir):
        return out
    for entry in sorted(os.listdir(depot_dir), key=str.lower):
        path = os.path.join(depot_dir, entry)
        if entry.startswith("."):
            continue
        if os.path.islink(path):
            out.append({"manifest": None, "path": path, "kind": "link", "notes": [f"{entry}: links are not followed"]})
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, "extension.json")):
            try:
                with open(os.path.join(path, "extension.json"), "rb") as f:
                    manifest, notes = _read_manifest(f.read(), f"{entry}/extension.json")
            except OSError as e:
                manifest, notes = None, [f"{entry}/extension.json could not be read ({e})"]
            out.append({"manifest": manifest, "path": path, "kind": "folder", "notes": notes})
        elif os.path.isfile(path) and entry.lower().endswith(PACKAGE_SUFFIXES):
            try:
                with zipfile.ZipFile(path) as z:
                    prefix = _zip_prefix(z)
                    if prefix is None:
                        out.append({"manifest": None, "path": path, "kind": "zip", "notes": [f"{entry}: no extension.json inside"]})
                        continue
                    manifest, notes = _read_manifest(z.read(prefix + "extension.json"), f"{entry}/extension.json")
            except (zipfile.BadZipFile, OSError, KeyError) as e:
                out.append({"manifest": None, "path": path, "kind": "zip", "notes": [f"{entry} could not be opened ({e})"]})
                continue
            out.append({"manifest": manifest, "path": path, "kind": "zip", "notes": notes})
    return out


def _zip_prefix(z):
    """'' when extension.json is at the root, 'name/' when it is in the only
    top-level folder, None when it is not there."""
    names = [n for n in z.namelist() if n and not n.endswith("/")]
    if "extension.json" in names:
        return ""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1:
        top = next(iter(tops))
        if f"{top}/extension.json" in names:
            return top + "/"
    return None


def status(manifest, installed):
    """How a package relates to what is installed: 'new', 'installed' (same
    version), 'update' (the package is newer), 'older' (the package is older)
    or 'incompatible' (needs a newer/older extension API than this Blockliner).
    `installed` is {extension id: extension_version}."""
    if X.compatibility(manifest)[0] != "ok":
        return "incompatible"
    have = installed.get(manifest["id"])
    if have is None:
        return "new"
    a, b = _ver(manifest["extension_version"]), _ver(have)
    return "update" if a > b else "installed" if a == b else "older"


# ---- installing --------------------------------------------------------------------
class DepotError(Exception):
    pass


def folder_name(ext_id):
    """'author/name' -> 'author-name' (a safe single folder name)."""
    return re.sub(r"[^a-z0-9_-]+", "-", ext_id.lower()).strip("-") or "extension"


def _safe_member(name):
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return False
    return ".." not in n.split("/")


def _extract_zip(path, dest):
    with zipfile.ZipFile(path) as z:
        prefix = _zip_prefix(z)
        if prefix is None:
            raise DepotError("The package has no extension.json.")
        infos = [i for i in z.infolist() if i.filename.startswith(prefix) and i.filename != prefix]
        if len(infos) > MAX_FILES:
            raise DepotError(f"The package has more than {MAX_FILES} files.")
        if sum(i.file_size for i in infos) > MAX_BYTES:
            raise DepotError("The package is larger than 50 MB unpacked.")
        for info in infos:
            rel = info.filename[len(prefix):]
            if not _safe_member(info.filename):
                raise DepotError(f"The package has an unsafe path: {info.filename}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise DepotError(f"The package contains a link: {info.filename}")
            target = os.path.join(dest, *rel.rstrip("/").split("/"))
            if os.path.commonpath([os.path.realpath(dest), os.path.realpath(target)]) != os.path.realpath(dest):
                raise DepotError(f"The package has an unsafe path: {info.filename}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _copy_folder(src, dest):
    count = total = 0
    for root, dirs, files in os.walk(src):
        for name in dirs + files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                raise DepotError(f"The package contains a link: {os.path.relpath(full, src)}")
        for name in files:
            count += 1
            total += os.path.getsize(os.path.join(root, name))
        if count > MAX_FILES or total > MAX_BYTES:
            raise DepotError("The package is too large.")
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        os.makedirs(os.path.join(dest, rel) if rel != "." else dest, exist_ok=True)
        for name in files:
            shutil.copyfile(os.path.join(root, name), os.path.join(dest, rel, name) if rel != "." else os.path.join(dest, name))


def install(package, user_root, existing_folder=None):
    """Copy a scanned package into `user_root` (the user's extensions folder).
    `existing_folder` is the folder of the installed copy being updated, replaced
    only if it is a real subfolder of user_root. Returns (ok, message). On any
    problem nothing is left half-installed."""
    manifest = package.get("manifest")
    if manifest is None:
        return False, "This package is damaged: " + "; ".join(package.get("notes") or ["no details"])
    if X.compatibility(manifest)[0] != "ok":
        return False, X.compatibility(manifest)[1]
    os.makedirs(user_root, exist_ok=True)
    final = existing_folder or os.path.join(user_root, folder_name(manifest["id"]))
    if existing_folder and os.path.dirname(os.path.realpath(existing_folder)) != os.path.realpath(user_root):
        return False, "The installed copy is not in your extensions folder, so it can't be replaced."
    if not existing_folder and os.path.exists(final):
        return False, f"A folder named {os.path.basename(final)} already exists in your extensions folder."
    stage = tempfile.mkdtemp(prefix=".install-", dir=user_root)
    old = None
    try:
        if package["kind"] == "zip":
            _extract_zip(package["path"], stage)
        elif package["kind"] == "folder":
            _copy_folder(package["path"], stage)
        else:
            raise DepotError("This package can't be installed.")
        with open(os.path.join(stage, "extension.json"), "rb") as f:
            check, notes = _read_manifest(f.read(), "extension.json")
        if check is None or check["id"] != manifest["id"]:
            raise DepotError("The unpacked extension.json does not match the package.")
        if os.path.exists(final):
            old = final + f".old-{os.getpid()}"
            os.rename(final, old)
        try:
            os.rename(stage, final)
        except OSError:
            if old:
                os.rename(old, final)
                old = None
            raise
        if old:
            shutil.rmtree(old, ignore_errors=True)
        return True, f"Installed {manifest['name']} {manifest['extension_version']}. It is off until you turn it on."
    except (DepotError, OSError, zipfile.BadZipFile) as e:
        return False, str(e)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---- starting a new extension ----------------------------------------------------
STARTER_MAIN = '''"""A Blockliner extension: it talks JSON lines on stdin/stdout.
Docs: docs/design-extensions.md in the Blockliner folder."""
import json
import sys


def send(obj):
    print(json.dumps(obj), flush=True)


for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("event") == "hello":
        send({"event": "ready", "params": {"api": ["1.0"]}})
        send({"id": 1, "method": "panel.set", "params": {"description": {
            "type": "column", "children": [
                {"type": "label", "text": "Hello from my extension", "style": "title"},
                {"type": "button", "text": "Say hi", "command": "hi"}]}}})
    elif msg.get("event") == "command" and msg["params"].get("command") == "hi":
        send({"id": 2, "method": "notify", "params": {"text": "Hi!"}})
    elif msg.get("event") == "shutdown":
        break
'''


def scaffold(depot_dir, name):
    """Create <depot>/<slug>/ with a working extension.json and main.py and
    return (folder | None, message). Never overwrites an existing folder."""
    name = (name or "").strip()
    slug = folder_name(name)
    if not name or not re.search(r"[a-z0-9]", name.lower()):
        return None, "Give the extension a name (letters or digits)."
    folder = os.path.join(depot_dir, slug)
    if os.path.exists(folder):
        return None, f"There is already a folder called {slug} in the depot."
    manifest = {
        "format": X.FORMAT, "version": 1, "id": f"local/{slug}", "name": name,
        "description": "My extension.", "author": "", "extension_version": "0.1.0",
        "requires": {"api": "1.0"}, "run": {"command": ["python3", "main.py"]},
        "permissions": ["ui.panel", "ui.notify"], "panel": {"title": name, "dock": "right", "width": 260},
    }
    os.makedirs(folder)
    with open(os.path.join(folder, "extension.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    with open(os.path.join(folder, "main.py"), "w", encoding="utf-8") as f:
        f.write(STARTER_MAIN)
    return folder, f"Created {folder}"
