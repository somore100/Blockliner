"""UI builder packs (pure, no Tk): data that teaches the builder one library.

Folder layout (see docs/ui-builder-design.md):

    ui_packs/
      python/                 one folder per language
        tkinter/              a pack that ships with the app
          pack.json
          widgets/*.json      one widget object, or a list of them, per file
        custom/               packs made by the user (writable), same shape
          my_pack/pack.json

pack.json (format 1):

    {"format": "blockliner-ui-pack", "version": 1,
     "id": "python/tkinter", "language": "python", "label": "tkinter",
     "imports": ["import tkinter as tk"],     emitted once, before the UI code
     "header": [],                            extra lines after the imports
     "root_types": ["window"],                widget types that may be the root
     "run": "{root}.mainloop()",
     "layouts": {"grid": {"props": [...], "code": "{name}.grid({args})"}},
     "preview": "native" | "boxes",           how the designer draws it
     "order": ["window", "label", ...],       optional palette order (others follow, by file)
     "widgets": [ ...optional inline widgets... ]}

A widget:

    {"type": "button", "label": "Button", "category": "Basic", "icon": "...",
     "container": false, "default_size": [100, 32],
     "props": [{"key": "text", "label": "Text", "kind": "string", "default": "Button"}, ...],
     "events": [{"key": "command", "label": "On click", "args": [],
                 "code": "{name}.configure(command={handler})"}],
     "code": "ttk.Button({parent}{opts})"  or  "code": ["line", "line"],
     "code_raw": "..."}                       optional escape hatch, used as-is

Code templates are plain strings with these placeholders (checked when the
pack loads; the generator in ui_gen.py fills them in):

    {name} {parent} {handler}   the widget's variable, its parent's, the event handler
    {args}                      every set, non-default, non-inline prop as `arg=value`, comma-joined
    {opts}                      the same with a leading ", " (empty when nothing is set)
    {key} {key!r}               one prop's value (`!r` = the language's quoted form)

Props marked "inline": true are left out of {args}/{opts}; the template places
them itself. A prop with "omit_when": X is left out when its value is X (the
library's own default), so generated code stays short. "default" is only the
value the designer gives a newly added widget.

The pack also says how to wrap the UI in a function that returns its widgets
as one namespace (ui.entry_name), and how to quote values:

     "quote": "python" | "json",
     "function": {"def": "def {fname}():", "indent": "    ",
                  "ret": "return types.SimpleNamespace({pairs})",
                  "pair": "{name}={name}", "call": "{ui} = {fname}()"},
     "run": "{ui}.{root}.mainloop()" Nothing here raises on bad input: problems become notes and a bad
pack or widget is skipped.
"""
import json
import os
import re
import string

FORMAT = "blockliner-ui-pack"
VERSION = 1
PROP_KINDS = ("string", "int", "float", "bool", "enum", "color", "font", "code", "list")
PREVIEWS = ("native", "boxes")
QUOTES = ("python", "json")
FUNCTION_FIELDS = {"def": ("fname",), "ret": ("pairs",), "pair": ("name",), "call": ("ui", "fname")}
GENERAL_FIELDS = ("name", "parent", "handler", "args", "opts")
_SAFE = re.compile(r"^[a-z0-9_]+$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_WIDGETS = 200
MAX_PROPS = 60


# --- template checking --------------------------------------------------------

def template_problems(text, allowed_fields):
    """Strings describing what is wrong with one code template ([] when fine)."""
    if not isinstance(text, str):
        return ["template is not text"]
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as e:
        return [f"bad braces ({e})"]
    out = []
    for _lit, field, spec, conv in parsed:
        if field is None:
            continue
        if field not in allowed_fields:
            out.append(f"unknown placeholder {{{field}}}")
        if conv not in (None, "r", "s"):
            out.append(f"unsupported conversion !{conv} on {{{field}}}")
        if spec:
            out.append(f"format spec on {{{field}}} isn't supported")
    return out


def template_text(code):
    """A template may be one string or a list of lines; returns the lines."""
    if isinstance(code, str):
        return code.split("\n")
    if isinstance(code, list) and all(isinstance(x, str) for x in code):
        return list(code)
    return None


# --- props ----------------------------------------------------------------

def _prop_default_ok(prop):
    d = prop.get("default")
    if d is None:
        return True
    kind = prop["kind"]
    if kind == "bool":
        return isinstance(d, bool)
    if kind == "int":
        return isinstance(d, int) and not isinstance(d, bool)
    if kind == "float":
        return isinstance(d, (int, float)) and not isinstance(d, bool)
    if kind == "enum":
        return d in prop["options"]
    if kind == "list":
        return isinstance(d, list)
    return isinstance(d, str)


def clean_props(raw, where, notes):
    """Validated copy of a props list (bad entries dropped with a note)."""
    out, seen = [], set()
    if raw is None:
        return out
    if not isinstance(raw, list):
        notes.append(f"{where}: 'props' is not a list")
        return out
    for p in raw[:MAX_PROPS]:
        if not isinstance(p, dict) or not isinstance(p.get("key"), str) or not _IDENT.match(p["key"]):
            notes.append(f"{where}: a prop needs a 'key' that is a plain identifier")
            continue
        key = p["key"]
        if key in GENERAL_FIELDS:
            notes.append(f"{where}: prop '{key}' clashes with a reserved placeholder")
            continue
        if key in seen:
            notes.append(f"{where}: prop '{key}' is listed twice")
            continue
        if p.get("kind") not in PROP_KINDS:
            notes.append(f"{where}: prop '{key}' has an unknown kind")
            continue
        if p["kind"] == "enum" and not (isinstance(p.get("options"), list) and p["options"]
                                        and all(isinstance(o, str) for o in p["options"])):
            notes.append(f"{where}: enum prop '{key}' needs a list of 'options'")
            continue
        if not _prop_default_ok(p):
            notes.append(f"{where}: prop '{key}' has a default that doesn't match its kind")
            continue
        seen.add(key)
        out.append({"key": key,
                    "label": p["label"] if isinstance(p.get("label"), str) else key,
                    "kind": p["kind"],
                    "default": p.get("default"),
                    "options": list(p.get("options") or []),
                    "arg": p["arg"] if isinstance(p.get("arg"), str) and _IDENT.match(p["arg"]) else key,
                    "inline": bool(p.get("inline")),
                    "optional": bool(p.get("optional")),
                    "omit_when": p.get("omit_when")})
    return out


# --- widgets --------------------------------------------------------------

def clean_widget(raw, where, notes):
    """Validated widget definition, or None (with a note)."""
    if not isinstance(raw, dict):
        notes.append(f"{where}: a widget is not an object")
        return None
    wtype = raw.get("type")
    if not isinstance(wtype, str) or not _SAFE.match(wtype):
        notes.append(f"{where}: a widget 'type' must be lowercase letters, digits and _")
        return None
    where = f"{where} ({wtype})"
    props = clean_props(raw.get("props"), where, notes)
    prop_keys = {p["key"] for p in props}
    fields = set(GENERAL_FIELDS) | prop_keys

    raw_code = raw.get("code_raw")
    lines = template_text(raw.get("code"))
    if raw_code is not None:
        if not isinstance(raw_code, str):
            notes.append(f"{where}: 'code_raw' must be text")
            return None
    elif lines is None:
        notes.append(f"{where}: needs 'code' (or 'code_raw')")
        return None
    else:
        for line in lines:
            for prob in template_problems(line, fields):
                notes.append(f"{where}: code: {prob}")
                return None

    events = []
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict) or not isinstance(ev.get("key"), str) or not ev["key"]:
            notes.append(f"{where}: an event needs a 'key'")
            continue
        elines = template_text(ev.get("code"))
        probs = [p for ln in (elines or []) for p in template_problems(ln, fields)]
        if elines is None or probs:
            notes.append(f"{where}: event '{ev['key']}' has bad code" + (f" ({probs[0]})" if probs else ""))
            continue
        events.append({"key": ev["key"],
                       "label": ev["label"] if isinstance(ev.get("label"), str) else ev["key"],
                       "args": [a for a in ev.get("args") or [] if isinstance(a, str)],
                       "code": elines})

    size = raw.get("default_size")
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(n, int) and n > 0 for n in size)):
        size = [100, 30]
    return {"type": wtype,
            "label": raw["label"] if isinstance(raw.get("label"), str) else wtype,
            "category": raw["category"] if isinstance(raw.get("category"), str) else "Other",
            "icon": raw["icon"] if isinstance(raw.get("icon"), str) else "",
            "container": bool(raw.get("container")),
            "default_size": size,
            "props": props, "events": events,
            "code": lines if raw_code is None else None,
            "code_raw": raw_code}


# --- the pack -------------------------------------------------------------

class Pack:
    def __init__(self, data, widgets, folder="", scope="prebuilt"):
        self.id = data["id"]
        self.language = data["language"]
        self.label = data["label"]
        self.imports = data["imports"]
        self.header = data["header"]
        self.root_types = data["root_types"]
        self.run = data["run"]
        self.quote = data["quote"]
        self.function = data["function"]
        self.layouts = data["layouts"]
        self.preview = data["preview"]
        self.widgets = widgets            # type -> definition, in file order
        self.folder = folder
        self.scope = scope

    def widget(self, wtype):
        return self.widgets.get(wtype)

    def is_container(self, wtype):
        w = self.widgets.get(wtype)
        return bool(w and w["container"])

    def defaults(self, wtype):
        """Starting props for a freshly added widget (only props with a default)."""
        w = self.widgets.get(wtype)
        return {p["key"]: p["default"] for p in (w["props"] if w else []) if p["default"] is not None}

    def palette(self):
        """[(category, [widget, ...])] in first-seen order; root types excluded
        (a window is the surface, not something you drop)."""
        order, groups = [], {}
        for w in self.widgets.values():
            if w["type"] in self.root_types:
                continue
            if w["category"] not in groups:
                groups[w["category"]] = []
                order.append(w["category"])
            groups[w["category"]].append(w)
        return [(c, groups[c]) for c in order]

    def tree_problems(self, tree):
        """Strings describing where a UITree doesn't fit this pack ([] = fine).
        Never raises; an unknown widget is a problem, not an error, so the
        designer can show it read-only instead of dropping it."""
        out = []
        if tree.pack_id and tree.pack_id != self.id:
            out.append(f"made for pack '{tree.pack_id}', not '{self.id}'")
        if tree.root["type"] not in self.root_types:
            out.append(f"root '{tree.root['type']}' isn't a root type of this pack")
        for node in tree.walk():
            w = self.widgets.get(node["type"])
            if w is None:
                out.append(f"'{node['name']}': unknown widget type '{node['type']}'")
                continue
            if node["children"] and not w["container"]:
                out.append(f"'{node['name']}': a {node['type']} can't contain widgets")
            known = {p["key"] for p in w["props"]}
            out.extend(f"'{node['name']}': unknown property '{k}'" for k in node["props"] if k not in known)
            events = {e["key"] for e in w["events"]}
            out.extend(f"'{node['name']}': unknown event '{k}'" for k in node["events"] if k not in events)
            manager = node["layout"].get("manager")
            if manager is not None and manager not in self.layouts:
                out.append(f"'{node['name']}': layout manager '{manager}' isn't in this pack")
        return out


def _clean_layouts(raw, where, notes):
    out = {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        notes.append(f"{where}: 'layouts' is not an object")
        return out
    for manager, spec in raw.items():
        if not isinstance(spec, dict) or not isinstance(manager, str) or not _SAFE.match(manager):
            notes.append(f"{where}: layout '{manager}' is malformed")
            continue
        props = clean_props(spec.get("props"), f"{where} layout {manager}", notes)
        lines = template_text(spec.get("code"))
        fields = set(GENERAL_FIELDS) | {p["key"] for p in props}
        if lines is None or any(template_problems(ln, fields) for ln in lines):
            notes.append(f"{where}: layout '{manager}' has bad code")
            continue
        out[manager] = {"props": props, "code": lines}
    return out


def _read_json(path, notes, label=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        notes.append(f"{label or os.path.basename(path)}: can't read ({e.__class__.__name__})")
        return None


def load_pack(folder, scope="prebuilt"):
    """(Pack | None, notes) for the pack in `folder`. Bad widgets are skipped
    with a note; a bad pack.json gives (None, notes)."""
    notes = []
    name = os.path.basename(os.path.normpath(folder))
    data = _read_json(os.path.join(folder, "pack.json"), notes, f"{name}/pack.json")
    if data is None:
        return None, notes
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None, notes + [f"{name}: pack.json isn't a Blockliner UI pack"]
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version > VERSION:
        return None, notes + [f"{name}: unsupported pack version {version!r}"]
    pid, lang = data.get("id"), data.get("language")
    if not (isinstance(pid, str) and isinstance(lang, str) and _SAFE.match(lang)
            and pid.startswith(lang + "/") and _SAFE.match(pid[len(lang) + 1:] or "!")):
        return None, notes + [f"{name}: 'id' must look like '<language>/<name>' and match 'language'"]
    for key in ("imports", "header", "root_types"):
        v = data.get(key, [])
        if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            return None, notes + [f"{name}: '{key}' must be a list of text"]
    if not data.get("root_types"):
        return None, notes + [f"{name}: 'root_types' is empty"]
    if data.get("preview", "boxes") not in PREVIEWS:
        notes.append(f"{name}: unknown preview mode, using 'boxes'")
    fn = data.get("function")
    if not (isinstance(fn, dict) and isinstance(fn.get("indent"), str) and fn["indent"].strip() == ""
            and all(isinstance(fn.get(k), str) and not template_problems(fn[k], allowed)
                    for k, allowed in FUNCTION_FIELDS.items())):
        return None, notes + [f"{name}: 'function' needs indent, def, ret, pair and call templates"]
    if template_problems(data.get("run", ""), ("ui", "root")):
        return None, notes + [f"{name}: 'run' may only use {{ui}} and {{root}}"]
    if data.get("quote", "python") not in QUOTES:
        return None, notes + [f"{name}: 'quote' must be one of {', '.join(QUOTES)}"]
    clean = {"id": pid, "language": lang, "quote": data.get("quote", "python"), "function": dict(fn),
             "label": data["label"] if isinstance(data.get("label"), str) else pid,
             "imports": data.get("imports", []), "header": data.get("header", []),
             "root_types": data["root_types"],
             "run": data["run"] if isinstance(data.get("run"), str) else "",
             "layouts": _clean_layouts(data.get("layouts"), name, notes),
             "preview": data.get("preview") if data.get("preview") in PREVIEWS else "boxes"}

    raws = [(f"{name}/pack.json", w) for w in (data.get("widgets") or [])]
    wdir = os.path.join(folder, "widgets")
    if os.path.isdir(wdir):
        for fn in sorted(os.listdir(wdir), key=str.lower):
            if not fn.endswith(".json") or fn.startswith("."):
                continue
            content = _read_json(os.path.join(wdir, fn), notes, f"{name}/widgets/{fn}")
            if content is None:
                continue
            for w in content if isinstance(content, list) else [content]:
                raws.append((f"{name}/widgets/{fn}", w))
    widgets = {}
    for where, raw in raws[:MAX_WIDGETS]:
        w = clean_widget(raw, where, notes)
        if w is None:
            continue
        if w["type"] in widgets:
            notes.append(f"{where}: widget '{w['type']}' is defined twice, keeping the first")
            continue
        widgets[w["type"]] = w
    order = [t for t in data.get("order") or [] if isinstance(t, str)]
    widgets = dict(sorted(widgets.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)))
    for rt in clean["root_types"]:
        if rt not in widgets:
            return None, notes + [f"{name}: root type '{rt}' has no widget definition"]
    return Pack(clean, widgets, folder, scope), notes


def find_packs(roots, language):
    """([Pack], notes): every valid pack for `language` under the given
    ui_packs roots, prebuilt ones then custom ones. The first pack with an id
    wins; roots that are the same real folder are only read once."""
    packs, notes, seen_ids, seen_dirs = [], [], set(), set()
    if not isinstance(language, str) or not _SAFE.match(language):
        return packs, notes
    for root in roots:
        lang_dir = os.path.join(root, language)
        real = os.path.realpath(lang_dir)
        if real in seen_dirs or not os.path.isdir(lang_dir):
            continue
        seen_dirs.add(real)
        for scope, base in (("prebuilt", lang_dir), ("custom", os.path.join(lang_dir, "custom"))):
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base), key=str.lower):
                folder = os.path.join(base, entry)
                if entry.startswith(".") or (scope == "prebuilt" and entry == "custom") \
                        or not os.path.isfile(os.path.join(folder, "pack.json")):
                    continue
                pack, pnotes = load_pack(folder, scope)
                notes.extend(pnotes)
                if pack is None:
                    continue
                if pack.id in seen_ids:
                    notes.append(f"{entry}: a pack with id '{pack.id}' is already loaded, skipped")
                    continue
                seen_ids.add(pack.id)
                packs.append(pack)
    return packs, notes
