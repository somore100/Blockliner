"""Read UI code back into a widget tree (pure, no Tk): the inverse of ui_gen.

It only understands the shape the generator writes. Each line of the build
function is matched against the pack's own templates run backwards, so it works
for any pack, not one library. Anything it can't match is ignored while reading,
and then the result is checked the safe way: the tree is generated again, and
unless that gives back exactly the code that was read, nothing is accepted and
the first difference is reported. So a successful read never loses anything the
user wrote, and edits to values, names, layout numbers and event links in the
code do come through.
"""
import ast
import re
import string

import ui_gen
import ui_node
from ui_tree import UITree

_IDENT = r"[A-Za-z_]\w*"


def _regex(template):
    """Template -> compiled regex. {opts}/{args} take everything they can;
    a field used twice must repeat the same text."""
    out, seen = [], set()
    for lit, field, _spec, _conv in string.Formatter().parse(template):
        out.append(re.escape(lit))
        if field is None:
            continue
        if field in seen:
            out.append(f"(?P={field})")
            continue
        seen.add(field)
        if field in ("name", "parent", "handler"):
            out.append(f"(?P<{field}>{_IDENT}(?:\\.{_IDENT})*)")
        elif field == "opts":
            out.append("(?P<opts>(?:, .*)?)")
        elif field == "args":
            out.append("(?P<args>.*)")
        else:
            out.append(f"(?P<{field}>.+?)")
    return re.compile("".join(out) + r"\Z")


def _kwargs(text):
    """{name: source text} from 'a=1, b="x"', or None when it isn't a call's argument list."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith(","):
        text = text[1:]
    try:
        call = ast.parse(f"f({text})", mode="eval").body
    except SyntaxError:
        return None
    if call.args or any(k.arg is None for k in call.keywords):
        return None
    return {k.arg: ast.get_source_segment(f"f({text})", k.value) for k in call.keywords}


def _value(kind, source):
    if kind == "code":
        return source
    try:
        return ast.literal_eval(source)
    except (ValueError, SyntaxError):
        return source


def _set_by_arg(schema, kwargs, target, skip_inline=False):
    """Copy keyword values into `target` under the props' keys. False if any
    keyword isn't one of the props."""
    by_arg = {p["arg"]: p for p in schema if not (skip_inline and p["inline"])}
    for arg, source in kwargs.items():
        p = by_arg.get(arg)
        if p is None:
            return False
        target[p["key"]] = _value(p["kind"], source)
    return True


def _body_lines(text):
    """(function name | None, [stripped statement lines]) of the first top-level def."""
    try:
        module = ast.parse(text)
    except SyntaxError:
        return None, []
    fn = next((n for n in module.body if isinstance(n, ast.FunctionDef)), None)
    if fn is None:
        return None, []
    lines = []
    for stmt in fn.body:
        seg = ast.get_source_segment(text, stmt)
        if seg is not None and "\n" not in seg:
            lines.append(seg.strip())
    return fn.name, lines


def parse(text, pack, handler_id=None, previous=None):
    """(tree | None, problems). handler_id(function name) -> node id or None.
    `previous` (a UITree) lends its editor-only data (device choice) to the new one."""
    fname, lines = _body_lines(text)
    if fname is None:
        return None, ["no function was found in the code"]
    creators = []
    for wtype, w in pack.widgets.items():
        if w["code"]:
            creators.append((wtype, w, _regex(w["code"][0]), [_regex(c) for c in w["code"][1:]]))
    layouts = {m: (spec, _regex(spec["code"][0])) for m, spec in pack.layouts.items() if len(spec["code"]) == 1}
    events = {}                                       # type -> [(event, regex)]
    for wtype, w in pack.widgets.items():
        events[wtype] = [(ev, _regex(ev["code"][0])) for ev in w["events"] if len(ev["code"]) == 1]

    tree, by_name, problems = None, {}, []
    i = 0
    while i < len(lines):
        text_line = lines[i]
        i += 1
        made = False
        for wtype, w, first, rest in creators:
            m = first.match(text_line)
            if not m:
                continue
            name = m.group("name")
            captured = dict(m.groupdict())
            ok = True
            for extra in rest:                        # the creation's further lines, e.g. title, size
                if i < len(lines) and (m2 := extra.match(lines[i])) and m2.group("name") == name:
                    captured.update(m2.groupdict())
                    i += 1
                else:
                    ok = False
                    break
            if not ok:
                continue
            props = {}
            for p in w["props"]:
                if p["inline"] and p["key"] in captured:
                    props[p["key"]] = _value(p["kind"], captured[p["key"]])
            opts = _kwargs(captured.get("opts", "")) if "opts" in captured else {}
            if opts is None or not _set_by_arg(w["props"], opts, props, skip_inline=True):
                problems.append(f"can't read the options in: {text_line}")
                made = True
                break
            parent = captured.get("parent")
            design = {"w": w["default_size"][0], "h": w["default_size"][1]}
            if tree is None:
                if wtype not in pack.root_types:
                    problems.append(f"the first widget must be a window, not '{wtype}'")
                    return None, problems
                tree = UITree.new(pack.id, root_type=wtype, root_name=name, props=props,
                                  is_container=pack.is_container)
                by_name[name] = (tree.root["id"], wtype)
            elif parent in by_name and wtype not in pack.root_types:
                try:
                    wid = tree.add(by_name[parent][0], wtype, name=name, props=props, design=design)
                except ValueError as e:
                    problems.append(str(e))
                    made = True
                    break
                by_name[name] = (wid, wtype)
            else:
                problems.append(f"'{name}' has no known parent ({parent})")
            made = True
            break
        if made or tree is None:
            continue
        for manager, (spec, rx) in layouts.items():
            m = rx.match(text_line)
            if m and m.group("name") in by_name:
                kwargs = _kwargs(m.group("args"))
                values = {"manager": manager}
                if kwargs is not None and _set_by_arg(spec["props"], kwargs, values):
                    tree.find(by_name[m.group("name")][0])["layout"] = values
                made = True
                break
        if made:
            continue
        for name, (wid, wtype) in by_name.items():
            for ev, rx in events.get(wtype, []):
                m = rx.match(text_line)
                if m and m.group("name") == name:
                    target = handler_id(m.group("handler")) if handler_id else None
                    if target is None:
                        problems.append(f"'{m.group('handler')}' isn't a function in this file")
                    else:
                        tree.find(wid)["events"][ev["key"]] = target
                    made = True
                    break
            if made:
                break
    if tree is None:
        return None, problems or ["no window was found in the code"]
    if previous is not None:
        old = {n["name"]: n for n in previous.walk()}
        for n in tree.walk():
            if n["name"] in old and old[n["name"]]["type"] == n["type"]:
                n["design"] = {**n["design"], **{k: v for k, v in old[n["name"]]["design"].items()}}
    tree._undo, tree._redo = [], []
    return tree, problems


def first_difference(a, b):
    """Short description of where two code texts first differ, or None."""
    la, lb = [x.rstrip() for x in a.strip().splitlines()], [x.rstrip() for x in b.strip().splitlines()]
    for n in range(max(len(la), len(lb))):
        x = la[n] if n < len(la) else "(end of code)"
        y = lb[n] if n < len(lb) else "(end of code)"
        if x != y:
            if n >= len(lb):
                return f"(missing) {x.strip()}"
            return y.strip() or "(empty line)"
    return None


def read_back(node, pack, text, handler_name=None, handler_id=None, previous=None):
    """The checked read: (tree | None, problems). `handler_name(id)` is what the
    generator uses (as in ui_node.generate_text), `handler_id(name)` its inverse.
    Accepts only when generating the tree again gives exactly `text`."""
    tree, problems = parse(text, pack, handler_id, previous)
    if tree is None:
        return None, problems
    scratch = dict(node)
    scratch[ui_node.UI_KEY] = tree.to_dict()
    again, _p = ui_node.generate_text(scratch, pack, handler_name)
    if again is None:
        return None, ["the code could not be turned back into a UI"]
    diff = first_difference(again, text)
    if diff is not None:
        return None, [f"the designer can't represent this part: {diff}"] + problems
    return tree, problems
