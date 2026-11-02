"""Libraries and imports (pure, no Tk): what each language's libraries offer,
the import lines they need, presets, and a tidy-up report.

A language pack may hold a `libraries/` folder with one JSON file per library:

    {"name": "time", "import": "import time", "namespace": "time",
     "description": "Time and delays", "installed_module": "time",
     "commands": [{"name": "sleep", "use": "time.sleep",
                   "signature": "time.sleep(seconds)", "does": "Waits for that many seconds"}]}

    name          what the user sees and ticks
    import        the exact line that brings it in (any language's syntax)
    aliases       other spellings of that line that count as imported
    namespace     optional: any `namespace.something` in the code counts as using it
    installed_module  Python only: the module name to look for on this computer
    commands      what it offers; `use` is the text that appears in code

Presets are named lists of library names ("App basic: tkinter, math, time").
Nothing here edits a file: the functions return lists and lines for the caller.
"""
import importlib.util
import json
import os
import re

_NAME = re.compile(r"^[\w .+-]{1,60}$")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _clean_library(raw, where, notes):
    if not isinstance(raw, dict):
        notes.append(f"{where}: not an object")
        return None
    name, line = raw.get("name"), raw.get("import")
    if not (isinstance(name, str) and _NAME.match(name)) or not isinstance(line, str) or not line.strip():
        notes.append(f"{where}: needs a 'name' and an 'import' line")
        return None
    commands = []
    for c in raw.get("commands") or []:
        if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip():
            use = c["use"] if isinstance(c.get("use"), str) and c["use"].strip() else c["name"]
            commands.append({"name": c["name"], "use": use,
                             "signature": c["signature"] if isinstance(c.get("signature"), str) else use + "()",
                             "does": c["does"] if isinstance(c.get("does"), str) else ""})
        else:
            notes.append(f"{where}: a command without a name was skipped")
    return {"name": name, "import": line.strip(),
            "aliases": [a.strip() for a in raw.get("aliases") or [] if isinstance(a, str)],
            "namespace": raw["namespace"] if isinstance(raw.get("namespace"), str) else "",
            "description": raw["description"] if isinstance(raw.get("description"), str) else "",
            "installed_module": raw["installed_module"] if isinstance(raw.get("installed_module"), str) else "",
            "commands": commands}


def load_libraries(folder):
    """({name: library}, [notes]) from the *.json files in `folder` (a missing
    folder is fine: no libraries)."""
    libs, notes = {}, []
    if not os.path.isdir(folder):
        return libs, notes
    for fn in sorted(os.listdir(folder), key=str.lower):
        if not fn.endswith(".json") or fn.startswith("."):
            continue
        raw = _read(os.path.join(folder, fn))
        lib = _clean_library(raw, fn, notes) if raw is not None else None
        if raw is None:
            notes.append(f"{fn}: could not be read")
        if lib is not None and lib["name"] not in libs:
            libs[lib["name"]] = lib
    return libs, notes


def load_presets(*paths):
    """[{"name", "description", "libraries": [..]}] from JSON files (a list, or
    {"presets": [...]}); later files add to earlier ones, same name replaces."""
    found = {}
    for path in paths:
        data = _read(path) if path else None
        items = data.get("presets") if isinstance(data, dict) else data
        for p in items if isinstance(items, list) else []:
            if isinstance(p, dict) and isinstance(p.get("name"), str) and isinstance(p.get("libraries"), list):
                found[p["name"]] = {"name": p["name"], "description": str(p.get("description") or ""),
                                    "libraries": [n for n in p["libraries"] if isinstance(n, str)]}
    return list(found.values())


def preset_libraries(preset, libs):
    """(known library names in order, unknown names) for a preset."""
    names = [n for n in preset["libraries"]]
    return [n for n in names if n in libs], [n for n in names if n not in libs]


# ---- imports ----------------------------------------------------------------
def _norm(line):
    return " ".join(line.split())


def import_lines(libs, names):
    """The import lines for the ticked libraries, in order, each once."""
    out = []
    for n in names:
        lib = libs.get(n)
        if lib and lib["import"] not in out:
            out.append(lib["import"])
    return out


def imported_names(libs, code_lines):
    """Names of the libraries whose import line (or an alias) is in the code."""
    present = {_norm(ln) for ln in code_lines}
    return [n for n, lib in libs.items() if _norm(lib["import"]) in present or any(_norm(a) in present for a in lib["aliases"])]


def installed(lib, language):
    """True/False for Python libraries (is the module on this computer);
    None when it can't be known (other languages, or no module given)."""
    if language != "python" or not lib.get("installed_module"):
        return None
    try:
        return importlib.util.find_spec(lib["installed_module"].split(".")[0]) is not None
    except (ImportError, ValueError):
        return False


def search_commands(libs, query, limit=20):
    """[(library, command)] for what the user typed: exact name first, then
    prefix, then anywhere in the name; the library name also matches."""
    q = query.strip().lower()
    if not q:
        return []
    scored = []
    for lib in libs.values():
        for c in lib["commands"]:
            name = c["name"].lower()
            if name == q:
                rank = 0
            elif name.startswith(q):
                rank = 1
            elif q in name:
                rank = 2
            elif q in lib["name"].lower():
                rank = 3
            else:
                continue
            scored.append((rank, c["name"].lower(), lib["name"], lib, c))
    scored.sort(key=lambda t: t[:3])
    return [(lib, c) for _r, _n, _l, lib, c in scored[:limit]]


def command_status(lib, imported, language):
    """'imported' | 'available' | 'not_installed' for the colour of a search result."""
    if lib["name"] in imported:
        return "imported"
    return "not_installed" if installed(lib, language) is False else "available"


# ---- tidy-up -----------------------------------------------------------------
def _uses(lib, code):
    """True when `code` (text without import lines) uses the library."""
    if lib["namespace"] and re.search(rf"(?<![\w.]){re.escape(lib['namespace'])}\s*\.", code):
        return True
    for c in lib["commands"]:
        if re.search(rf"(?<![\w.]){re.escape(c['use'])}(?!\w)", code):
            return True
    return False


def tidy_report(libs, code_lines):
    """What a file's imports need, as lists the caller can show and offer to fix:

        missing     libraries the code uses but does not import
        unused      imported libraries the code never uses (only judged when the
                    library has a namespace, because otherwise Blockliner can't
                    know every command it offers)
        duplicates  import lines that appear more than once
    """
    import_set = {_norm(lib["import"]) for lib in libs.values()}
    for lib in libs.values():
        import_set.update(_norm(a) for a in lib["aliases"])
    body = "\n".join(ln for ln in code_lines if _norm(ln) not in import_set)
    have = set(imported_names(libs, code_lines))
    seen, duplicates = set(), []
    for ln in code_lines:
        key = _norm(ln)
        if key in import_set:
            if key in seen and key not in duplicates:
                duplicates.append(key)
            seen.add(key)
    missing = [n for n, lib in libs.items() if n not in have and _uses(lib, body)]
    unused = [n for n in have if libs[n]["namespace"] and not _uses(libs[n], body)]
    return {"missing": missing, "unused": unused, "duplicates": duplicates}


def dedupe_imports(libs, code_lines):
    """`code_lines` without repeated import lines (first one stays)."""
    import_set = {_norm(lib["import"]) for lib in libs.values()}
    seen, out = set(), []
    for ln in code_lines:
        key = _norm(ln)
        if key in import_set:
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return out


def qualified_index(libs):
    """{namespace: {"lib": library name, "methods": {names}}} for the line
    check: what `time.` or `tk.` may be followed by."""
    index = {}
    for name, lib in libs.items():
        ns = lib["namespace"]
        if not ns:
            continue
        entry = index.setdefault(ns, {"lib": name, "methods": set()})
        for c in lib["commands"]:
            if c["use"].startswith(ns + "."):
                entry["methods"].add(c["use"][len(ns) + 1:].split(".")[0])
    return index


def raw_import_blocks(libs, blocks, raw_id, raw_param):
    """[(index, library name)] of top-level blocks that are only a library's
    import line typed by hand (as a Raw Code block)."""
    by_line = {}
    for name, lib in libs.items():
        for line in [lib["import"]] + lib["aliases"]:
            by_line[_norm(line)] = name
    found = []
    for i, (block_id, params) in enumerate(blocks):
        if block_id == raw_id and isinstance(params, dict):
            name = by_line.get(_norm(str(params.get(raw_param, ""))))
            if name:
                found.append((i, name))
    return found


def used_by(lib, code_lines):
    """The first command of `lib` found in the code (for 'used by time.sleep'), or ''."""
    body = "\n".join(code_lines)
    for c in lib["commands"]:
        if re.search(rf"(?<![\w.]){re.escape(c['use'])}(?!\w)", body):
            return c["use"]
    return lib["namespace"] + "." if lib["namespace"] and re.search(rf"(?<![\w.]){re.escape(lib['namespace'])}\s*\.", body) else ""


def save_preset(path, name, library_names):
    """Add or replace one preset in the user's presets file; True when written."""
    existing = load_presets(path)
    kept = [p for p in existing if p["name"] != name]
    kept.append({"name": name, "description": "", "libraries": list(library_names)})
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"presets": kept}, f, indent=2)
        return True
    except OSError:
        return False
