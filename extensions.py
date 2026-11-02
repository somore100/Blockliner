"""Extensions (pure, no Tk): reading manifests, checking compatibility, deciding
what is enabled and what goes where in the interface. See docs/design-extensions.md.

An extension is a folder with an extension.json. Reading is "warn and skip": a
damaged manifest gives a note and that one extension is left out; nothing raises.
This file never runs extension code.
"""
import json
import os
import re

API_VERSION = (1, 0)                 # the extension API Blockliner speaks (major, minor)
FORMAT = "blockliner-extension"
MANIFEST_VERSION = 1
MAX_PINNED = 3                       # icons in the top bar before the "..." menu takes the rest

_ID = re.compile(r"^[a-z0-9_-]+/[a-z0-9_-]+$")
_VERSION = re.compile(r"^\d+(\.\d+){0,2}$")

PERMISSIONS = {
    "ui.panel": "Show a side panel and an icon",
    "ui.menu": "Add menu entries",
    "ui.notify": "Show messages",
    "project.read": "Read the open project (nodes, blocks, imports)",
    "project.write": "Change the open project (each change can be undone)",
    "files.read": "Read files in folders you pick for it",
    "files.write": "Write files in folders you pick for it",
    "net": "Talk to the network (not enforced: only install extensions you trust)",
    "exec": "Start other programs (not enforced: only install extensions you trust)",
}
DOCKS = ("left", "right")


def parse_version(text):
    """'1.2' -> (1, 2); '1' -> (1, 0); None when it isn't a version."""
    if not isinstance(text, str) or not _VERSION.match(text.strip()):
        return None
    parts = [int(p) for p in text.strip().split(".")]
    return tuple((parts + [0, 0])[:3]) if len(parts) > 2 else tuple((parts + [0])[:2])


def _text(raw, key, default=""):
    v = raw.get(key)
    return v.strip() if isinstance(v, str) else default


def clean_manifest(raw, where="extension.json"):
    """(manifest | None, notes). A manifest that can't be used gives None."""
    notes = []
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        return None, [f"{where}: not a Blockliner extension manifest"]
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version > MANIFEST_VERSION:
        return None, [f"{where}: unsupported manifest version {version!r}"]
    ext_id = _text(raw, "id")
    if not _ID.match(ext_id):
        return None, [f"{where}: 'id' must look like 'author/name' (lowercase letters, digits, - and _)"]
    name = _text(raw, "name")
    if not name:
        return None, [f"{where}: needs a 'name'"]
    requires = raw.get("requires") if isinstance(raw.get("requires"), dict) else {}
    api = parse_version(requires.get("api")) if "api" in requires else API_VERSION
    if api is None:
        return None, [f"{where}: 'requires.api' must look like '1.0'"]
    perms = []
    for p in raw.get("permissions") or []:
        if p in PERMISSIONS:
            perms.append(p)
        else:
            notes.append(f"{where}: unknown permission {p!r} ignored")
    panel = None
    if isinstance(raw.get("panel"), dict):
        pr = raw["panel"]
        width = pr.get("width")
        panel = {"title": _text(pr, "title") or name,
                 "dock": pr.get("dock") if pr.get("dock") in DOCKS else "right",
                 "width": width if isinstance(width, int) and not isinstance(width, bool) and 120 <= width <= 1000 else 280}
    run = None
    if isinstance(raw.get("run"), dict):
        cmd = raw["run"].get("command")
        if isinstance(cmd, list) and cmd and all(isinstance(c, str) and c for c in cmd):
            run = list(cmd)
        else:
            notes.append(f"{where}: 'run.command' must be a list of text (not a shell string); the extension can't be started")
    commands = []
    for m in raw.get("menus") or []:
        if isinstance(m, dict) and _text(m, "label") and _text(m, "command"):
            commands.append({"label": _text(m, "label"), "command": _text(m, "command"), "menu": _text(m, "menu") or "Tools"})
        else:
            notes.append(f"{where}: a menu entry needs a 'label' and a 'command' and was skipped")
    return {
        "id": ext_id, "name": name, "description": _text(raw, "description"), "author": _text(raw, "author"),
        "extension_version": _text(raw, "extension_version", "0.0.0"),
        "requires_api": api, "requires_app": _text(requires, "app"),
        "icon": _text(raw, "icon")[:4] or "⚙",
        "permissions": perms, "panel": panel, "commands": commands,
        "builtin": _text(raw, "builtin"),
        "run": run,
        "pin": bool(raw["pin"]) if "pin" in raw else panel is not None,
        "enabled_by_default": bool(raw.get("enabled_by_default", False)),
    }, notes


def find_extensions(roots):
    """[Extension] from folders: each root is (path, scope). An Extension is
    {"manifest", "folder", "scope", "notes"}; a broken one has manifest None.
    The first extension with an id wins."""
    found, seen = [], set()
    for root, scope in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root), key=str.lower):
            folder = os.path.join(root, entry)
            path = os.path.join(folder, "extension.json")
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, ValueError) as e:
                found.append({"manifest": None, "folder": folder, "scope": scope,
                              "notes": [f"{entry}/extension.json could not be read ({e})"]})
                continue
            manifest, notes = clean_manifest(raw, f"{entry}/extension.json")
            if manifest is None:
                found.append({"manifest": None, "folder": folder, "scope": scope, "notes": notes})
                continue
            if manifest["id"] in seen:
                continue
            seen.add(manifest["id"])
            if scope != "built-in":
                manifest["builtin"] = ""             # only shipped extensions may use built-in code
            found.append({"manifest": manifest, "folder": folder, "scope": scope, "notes": notes})
    return found


# ---- compatibility ------------------------------------------------------------
def compatibility(manifest, api=API_VERSION):
    """(status, reason): status is 'ok', 'newer_needed' (built for a newer API
    than this Blockliner speaks) or 'older_api' (built for an older major)."""
    need = manifest["requires_api"]
    if need[0] > api[0] or (need[0] == api[0] and need[1] > api[1]):
        return "newer_needed", f"Needs extension API {need[0]}.{need[1]}; this Blockliner speaks {api[0]}.{api[1]}. Update Blockliner."
    if need[0] < api[0]:
        return "older_api", f"Built for extension API {need[0]}.x, which this Blockliner no longer speaks. Update the extension."
    return "ok", ""


STATUS_TEXT = {"ok": "Compatible", "newer_needed": "Needs a newer Blockliner", "older_api": "Built for an older API"}


# ---- what is on ---------------------------------------------------------------
def enabled_map(settings):
    value = (settings if isinstance(settings, dict) else {}).get("extensions_enabled")
    return value if isinstance(value, dict) else {}


def is_enabled(manifest, settings):
    """The user's choice if there is one, else the manifest's default (off)."""
    choice = enabled_map(settings).get(manifest["id"])
    return choice if isinstance(choice, bool) else manifest["enabled_by_default"]


def set_enabled(settings, ext_id, value):
    settings.setdefault("extensions_enabled", {})
    if not isinstance(settings["extensions_enabled"], dict):
        settings["extensions_enabled"] = {}
    settings["extensions_enabled"][ext_id] = bool(value)


def safe_start(settings, environ=None):
    """True when everything should start switched off (a broken extension can
    always be turned off this way)."""
    env = environ if environ is not None else os.environ
    return bool(env.get("BLOCKLINER_SAFE")) or bool((settings or {}).get("extensions_safe_start"))


def active(exts, settings, environ=None):
    """Extensions that are enabled, compatible and usable; empty in safe start."""
    if safe_start(settings, environ):
        return []
    out = []
    for e in exts:
        m = e["manifest"]
        if m and compatibility(m)[0] == "ok" and is_enabled(m, settings):
            out.append(e)
    return out


def layout(active_exts, max_pinned=MAX_PINNED):
    """Where things go: {"pinned": [ext with a panel, in the top bar],
    "overflow_panels": [ext], "commands": [(ext, command)]} for the "..." menu."""
    with_panel = [e for e in active_exts if e["manifest"]["panel"]]
    pinned = [e for e in with_panel if e["manifest"]["pin"]][:max_pinned]
    rest = [e for e in with_panel if e not in pinned]
    commands = [(e, c) for e in active_exts for c in e["manifest"]["commands"]]
    return {"pinned": pinned, "overflow_panels": rest, "commands": commands}
