"""UI builder code generator (pure, no Tk): UITree + Pack -> source lines.

Deterministic: the same tree and pack always give the same text, so diffs and
undo stay clean. Output shape (for the tkinter pack):

    def build_main():
        root = tk.Tk()
        root.title('My app')
        btn_save = ttk.Button(root, text='Save')
        btn_save.grid(row=0, column=0)
        btn_save.configure(command=on_save)
        return types.SimpleNamespace(root=root, btn_save=btn_save)

    ui = build_main()
    ui.root.mainloop()

Widgets are emitted parent-first in tree order. Every language detail (calls,
quoting, how the function wraps up) comes from the pack; nothing here is
specific to a library. Nothing raises on odd input: a widget the pack doesn't
know is skipped and reported in `problems`.
"""
import json
import string

import ui_pack


def literal(kind, value, quote="python"):
    """`value` written as a literal of its kind in the target language."""
    if value is None:
        return "None" if quote == "python" else "null"
    if kind == "code":
        return str(value)
    if quote == "json":
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(literal("string" if isinstance(v, str) else "code", v, quote) for v in value) + "]"
    return repr(str(value))


def plain(value):
    """`value` as bare text (what {prop} without !r inserts)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def fill(template, values):
    """Substitute {field} / {field!r}. `values` maps a field to (plain, literal)."""
    out = []
    for lit, field, _spec, conv in string.Formatter().parse(template):
        out.append(lit)
        if field is not None:
            raw, quoted = values[field]
            out.append(quoted if conv == "r" else raw)
    return "".join(out)


def _prop_values(props_schema, node_values, quote):
    """{key: (plain, literal)} for every prop in the schema; unset falls back
    to the designer default, then to None."""
    out = {}
    for p in props_schema:
        value = node_values.get(p["key"], p["default"])
        out[p["key"]] = (plain(value), literal(p["kind"], value, quote))
    return out


def _args(props_schema, node_values, quote):
    """`key=value` for every set prop, schema order, skipping inline props,
    unset (None) props and values equal to the prop's omit_when."""
    parts = []
    for p in props_schema:
        if p["inline"] or p["key"] not in node_values:
            continue
        value = node_values[p["key"]]
        if value is None or (p["omit_when"] is not None and value == p["omit_when"]):
            continue
        parts.append(f"{p['arg']}={literal(p['kind'], value, quote)}")
    return ", ".join(parts)


def _template_values(name, parent, handler, props_schema, node_values, quote):
    args = _args(props_schema, node_values, quote)
    values = {"name": (name, name), "parent": (parent or "", parent or ""),
              "handler": (handler or "", handler or ""),
              "args": (args, args), "opts": ((", " + args) if args else "",) * 2}
    values.update(_prop_values(props_schema, node_values, quote))
    return values


def generate(tree, pack, handler_name=None, function_name=None, ui_name="ui"):
    """Returns {"imports", "function", "call", "run", "problems"}, each a list of lines.

    handler_name(target_id) -> the function's name for an event link, or None
    when it can't be resolved (the event is then skipped and reported).
    function_name defaults to build_<root name>."""
    problems = list(pack.tree_problems(tree))
    quote = pack.quote
    fn = pack.function
    fname = function_name or f"build_{tree.root['name']}"
    body, names = [], []

    def emit(node, parent_name):
        w = pack.widget(node["type"])
        if w is None:
            return                                  # reported by tree_problems
        name = node["name"]
        names.append(name)
        values = _template_values(name, parent_name, None, w["props"], node["props"], quote)
        if w["code_raw"] is not None:
            body.extend(w["code_raw"].replace("{name}", name).replace("{parent}", parent_name or "").split("\n"))
        else:
            body.extend(fill(line, values) for line in w["code"])

        manager = node["layout"].get("manager")
        if parent_name is not None:
            spec = pack.layouts.get(manager)
            if spec is not None:
                set_values = {k: v for k, v in node["layout"].items() if k != "manager"}
                lvals = _template_values(name, parent_name, None, spec["props"], set_values, quote)
                body.extend(fill(line, lvals) for line in spec["code"])
            elif manager is None:
                problems.append(f"'{name}' has no layout manager, so it won't be placed")

        for ev in w["events"]:
            target = node["events"].get(ev["key"])
            if target is None:
                continue
            handler = handler_name(target) if handler_name else None
            if not handler:
                problems.append(f"'{name}': the {ev['key']} event points at a function that can't be found")
                continue
            evals = _template_values(name, parent_name, handler, w["props"], node["props"], quote)
            body.extend(fill(line, evals) for line in ev["code"])

        for child in node["children"]:
            emit(child, name)

    emit(tree.root, None)
    indent = fn["indent"]
    pairs = ", ".join(fill(fn["pair"], {"name": (n, n)}) for n in names)
    function = [fill(fn["def"], {"fname": (fname, fname)})]
    function += [indent + line if line else line for line in body]
    function.append(indent + fill(fn["ret"], {"pairs": (pairs, pairs)}))
    ui_vals = {"ui": (ui_name, ui_name), "fname": (fname, fname), "root": (tree.root["name"],) * 2}
    imports = []
    for line in list(pack.imports) + list(pack.header):
        if line not in imports:
            imports.append(line)
    call = [fill(fn["call"], ui_vals)]
    run = [fill(pack.run, ui_vals)] if pack.run else []
    root_def = pack.widget(tree.root["type"])
    standalone = bool(root_def and root_def.get("no_run"))     # e.g. a popup: another window opens it
    return {"imports": imports, "function": function,
            "call": [] if standalone else call, "run": [] if standalone else run,
            "preview_tail": call + run, "problems": problems}


def render(result, include_run=True, preview=False):
    """The result as one block of source text. `preview` always ends with the
    call and run lines, even for a popup that normally has none."""
    tail = result["preview_tail"] if preview else result["call"] + (result["run"] if include_run else [])
    sections = [result["imports"], result["function"], tail]
    return "\n\n".join("\n".join(s) for s in sections if s) + "\n"
