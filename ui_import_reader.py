"""Read a HAND-WRITTEN UI program into a designer tree (pure, no Tk).

ui_parse reads only the exact shape the generator writes. This reads ordinary code: a script that creates a window
(`root = tk.Tk()`), widgets (`btn = tk.Button(root, text="Go", command=go)`) and places them (`btn.grid(row=0,
column=0)`). The pack's own widget templates say which class is which widget, so any pack whose widgets are plain
`name = Class(parent, key=value)` calls works (tkinter, customtkinter).

Nothing the author wrote is lost, and nothing is guessed:
  * what the pack understands becomes widgets, props, layout and event links;
  * a keyword the pack has no prop for stays as the widget's `extra` option, written back exactly as it was;
  * any other statement that touches the window or a widget (a loop that makes buttons, `entry.focus()`,
    `root.resizable(0, 0)`) is kept verbatim in the build function (`pre_code` before the widgets, `post_code` after);
  * code that doesn't (functions, classes, imports, plain variables) stays outside as ordinary code: `before` runs
    ahead of the window, `after` runs once the window has closed;
  * a statement the designer can't place safely (.pack(), a tk widget given ttk-only... options) stays verbatim too,
    and the report says so.
The window's widgets are copied into the module's globals (`expose_globals`), so handlers that use `entry.get()` by
name keep working.
"""
import ast
import re
import textwrap
from dataclasses import dataclass, field

import ui_import_class
from ui_tree import UITree, is_valid_name

ROOT_CLASSES = {"Tk", "CTk"}
ALIASES = {"bg": "background", "fg": "foreground"}
# keywords a ttk widget understands that the pack has no prop for: a tk widget that uses only these (and the pack's
# props) can safely become the pack's ttk widget
TTK_SAFE = {"textvariable", "variable", "image", "compound", "anchor", "justify", "wraplength", "underline", "cursor",
            "takefocus", "style", "padding", "class_", "name", "command", "values", "exportselection", "xscrollcommand",
            "yscrollcommand", "validate", "validatecommand", "invalidcommand", "show", "foreground", "background"}
_TEMPLATE_RE = re.compile(r"\{name\}\s*=\s*(?:(\w+)\.)?(\w+)\(")


@dataclass
class Result:
    tree: object = None
    before: str = ""                 # code that stays outside and runs before the window
    after: str = ""                  # code that stays outside and runs after the window closes
    links: list = field(default_factory=list)       # [(widget name, event key, handler function name)]
    report: list = field(default_factory=list)      # what happened, for the user
    problems: list = field(default_factory=list)    # why nothing could be read (tree is None)
    widgets: int = 0


def class_map(pack):
    """{class name: (widget type, module the pack uses)} from the pack's own templates."""
    out = {}
    for wtype, w in pack.widgets.items():
        if not w["code"]:
            continue
        m = _TEMPLATE_RE.match(w["code"][0])
        if m and wtype not in out.values():
            out.setdefault(m.group(2), (wtype, m.group(1)))
    return out


def _callee(call):
    """(module or None, class name) of `tk.Button(...)` / `Button(...)`, else (None, None)."""
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id, f.attr
    if isinstance(f, ast.Name):
        return None, f.id
    return None, None


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


_CONSTS = {"LEFT": "left", "RIGHT": "right", "TOP": "top", "BOTTOM": "bottom", "X": "x", "Y": "y", "BOTH": "both",
           "NONE": "none", "HORIZONTAL": "horizontal", "VERTICAL": "vertical", "YES": True, "NO": False,
           "NORMAL": "normal", "DISABLED": "disabled", "WORD": "word", "CHAR": "char", "CENTER": "center",
           "FLAT": "flat", "RAISED": "raised", "SUNKEN": "sunken", "GROOVE": "groove", "RIDGE": "ridge"}
_CONST_RE = re.compile(r"(?:tk|tkinter)\.([A-Z]+)\Z")


def _literal(source):
    """(ok, value): a literal, or a tkinter constant (tk.LEFT -> 'left'; the generated code uses the plain text)."""
    try:
        return True, ast.literal_eval(source)
    except (ValueError, SyntaxError):
        m = _CONST_RE.match(source)
        if m and m.group(1) in _CONSTS:
            return True, _CONSTS[m.group(1)]
        return False, None


def _fit(kind, value):
    """A bool setting written as 1/0 (expand=1) is a bool."""
    return bool(value) if kind == "bool" and value in (0, 1) and not isinstance(value, bool) else value


def read(source, pack):
    """Read `source` with `pack` (a ui_pack.Pack). Always returns a Result; `tree` is None when no window was found."""
    if pack.id == "python/kivy":
        import ui_import_kivy
        return ui_import_kivy.read(source, pack, Result)
    res = Result()
    try:
        module = ast.parse(source)
    except SyntaxError as e:
        res.problems.append(f"the code has a syntax error (line {e.lineno})")
        return res
    classes = class_map(pack)
    body = _flatten(module.body, pack, res)
    flat, why = ui_import_class.flatten(source)             # class App(tk.Tk): ... written out as plain code
    if flat is not None:
        again = read(flat, pack)
        again.report = why + again.report
        return again
    root_i = next((i for i, st in enumerate(body) if _root_name(st, pack)), None)
    if root_i is None:
        if why:
            res.problems.append("the window is made inside a class that can't be turned into plain code: " + "; ".join(why))
            return res
        in_class = any(isinstance(st, ast.ClassDef) and any(_callee_name(b) in ROOT_CLASSES for b in st.bases) for st in body)
        res.problems.append(
            "the window is made inside a class (class App(tk.Tk)), which isn't read yet" if in_class else
            "no window was found (a line like  root = tk.Tk()  at the top level of the code, in main(), or under if __name__ == '__main__')")
        return res
    root_name = _root_name(body[root_i], pack)
    root_type = pack.root_types[0]
    main_i = next((i for i in range(root_i + 1, len(body)) if _is_call_on(body[i], root_name, "mainloop")), len(body))

    def text(st):
        return textwrap.dedent(ast.get_source_segment(source, st, padded=True) or "")

    props = pack.defaults(root_type)
    tree = UITree.new(pack.id, root_type=root_type, root_name=root_name, props=props, is_container=pack.is_container)
    known = {root_name: tree.root["id"]}          # variable name -> widget id
    types = {root_name: root_type}
    before, after, pre, post = [], [], [], []
    seen_widget = False
    ui_names = set(known)                        # every name the window's code defines (widgets, variables made in it)
    notes = res.report

    for st in body[:root_i]:
        before.append(text(st))
    for st in body[root_i + 1:main_i]:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            before.append(text(st))
            continue
        if _window_call(st, root_name, tree.root["props"]):
            continue
        made = _widget(st, tree, pack, classes, known, types, res)
        if made == "ok":
            seen_widget = True
            ui_names.add(st.targets[0].id)
            continue
        if _layout_call(st, tree, pack, known, types, res):
            continue
        refs = _names(st)
        if refs & (ui_names | {"tk", "ttk", "tkinter", "ctk", "customtkinter"}):
            (post if seen_widget else pre).append(text(st))
            ui_names |= {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            if made == "verbatim":
                notes.append(f"kept as code (the designer can't place it): {text(st).splitlines()[0][:70]}")
        else:
            before.append(text(st))
    for st in body[main_i + 1:]:
        after.append(text(st))

    tree.extra["pre_code"], tree.extra["post_code"] = pre, post
    tree.extra["expose_globals"] = True
    tree._undo, tree._redo = [], []
    res.tree = tree
    res.before = "\n\n".join(x for x in before if x.strip())
    res.after = "\n\n".join(x for x in after if x.strip())
    res.widgets = sum(1 for _ in tree.walk()) - 1
    if pre or post:
        notes.append(f"{len(pre) + len(post)} statement(s) around the widgets are kept as code inside the window's function")
    return res


def _callee_name(node):
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)


def _has_root(stmts, pack):
    return any(_root_name(st, pack) for st in stmts)


def _flatten(body, pack, res):
    """The statements to read: the module's, or - when the window is made inside `if __name__ == "__main__":` or a
    function without parameters - that block's, taken out as if written at the top (a call of that function is dropped)."""
    if _has_root(body, pack):
        return body
    for i, st in enumerate(body):
        guard = (isinstance(st, ast.If) and isinstance(st.test, ast.Compare) and isinstance(st.test.left, ast.Name)
                 and st.test.left.id == "__name__")
        func = (isinstance(st, ast.FunctionDef) and not st.args.args and not st.args.vararg and not st.args.kwonlyargs)
        if (guard or func) and _has_root(st.body, pack):
            def calls_it(x):
                return (isinstance(x, ast.Expr) and isinstance(x.value, ast.Call) and isinstance(x.value.func, ast.Name)
                        and x.value.func.id == st.name)
            rest = [x for x in body[i + 1:] if not (func and (calls_it(x) or (
                isinstance(x, ast.If) and x.body and all(calls_it(y) for y in x.body) and not x.orelse)))]
            res.report.append(f"the window was made inside {'`if __name__ == \'__main__\'`' if guard else 'main()'}; "
                              "its code now runs at the top of the file")
            return body[:i] + list(st.body) + rest
    return body


def _root_name(st, pack):
    if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
            and isinstance(st.value, ast.Call):
        _mod, cls = _callee(st.value)
        if cls in ROOT_CLASSES:
            return st.targets[0].id
    return None


def _is_call_on(st, name, method):
    return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute)
            and isinstance(st.value.func.value, ast.Name) and st.value.func.value.id == name
            and st.value.func.attr == method)


def _window_call(st, root_name, props):
    """root.title("x") / root.geometry("400x300") with plain strings: the window's props."""
    for method in ("title", "geometry"):
        if _is_call_on(st, root_name, method):
            call = st.value
            if len(call.args) == 1 and not call.keywords and isinstance(call.args[0], ast.Constant) \
                    and isinstance(call.args[0].value, str):
                props[method] = call.args[0].value
                return True
    return False


def _widget(st, tree, pack, classes, known, types, res):
    """'ok' (a widget was added), 'verbatim' (a widget statement the designer can't take) or None (not one)."""
    if not (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
            and isinstance(st.value, ast.Call)):
        return None
    mod, cls = _callee(st.value)
    if cls not in classes and not (cls == "Scrollbar" and "scrollbar" in pack.widgets):
        return None
    name, call = st.targets[0].id, st.value
    kwargs = {k.arg: k.value for k in call.keywords}
    if None in kwargs or any(isinstance(a, ast.Starred) for a in call.args):
        return "verbatim"
    parent_node = call.args[0] if call.args else kwargs.pop("master", None)
    if len(call.args) > 1 or not isinstance(parent_node, ast.Name) or parent_node.id not in known:
        return "verbatim"
    if cls == "Scrollbar":
        horizontal = "orient" in kwargs and _is_horizontal(kwargs["orient"])
        wtype = "hscrollbar" if horizontal else "scrollbar"
        if wtype not in pack.widgets:
            return "verbatim"
        kwargs.pop("orient", None)
        module = classes.get("Scrollbar", (wtype, "ttk"))[1]
    else:
        wtype, module = classes[cls]
    w = pack.widget(wtype)
    if w is None or wtype in pack.root_types or not pack.is_container(types[parent_node.id]):
        return "verbatim"
    by_arg = {p["arg"]: p for p in w["props"] if not p["inline"]}
    events = {e["key"]: e for e in w["events"]}
    props, extra, links = {}, {}, []
    for arg, node in kwargs.items():
        src = _src(node)
        key = ALIASES.get(arg, arg)
        p = by_arg.get(key)
        if arg in events and isinstance(node, ast.Name):
            links.append((arg, node.id))
            continue
        if p is not None:
            ok, val = _literal(src)
            if ok and not isinstance(val, (set, dict)):
                props[p["key"]] = _fit(p["kind"], val)
                continue
        extra[arg] = src
    if module == "ttk" and mod != "ttk":
        # a plain tk widget becomes the pack's themed one: only when nothing it was given is lost
        bad = [a for a in kwargs if ALIASES.get(a, a) not in by_arg and a not in TTK_SAFE and a not in events]
        if bad:
            res.report.append(f"'{name}' uses {', '.join(sorted(bad))}, which the themed {wtype} doesn't take, so it stays as code")
            return "verbatim"
    try:
        wid = tree.add(known[parent_node.id], wtype, name=name, props=props, design={"w": w["default_size"][0], "h": w["default_size"][1]})
    except ValueError:
        return "verbatim"
    node_dict = tree.find(wid)
    if node_dict["name"] != name:                 # the name was taken (a variable reused): keep the statement as code
        tree.remove(wid)
        return "verbatim"
    if extra:
        node_dict["extra"] = extra
        res.report.append(f"'{name}': other options kept as written ({', '.join(extra)})")
    for key, handler in links:
        res.links.append((name, key, handler))
    known[name], types[name] = wid, wtype
    return "ok"


def _is_horizontal(node):
    src = _src(node)
    return "HORIZONTAL" in src.upper() or "horizontal" in src


def _src(node):
    return ast.unparse(node)


def _layout_call(st, tree, pack, known, types, res):
    """name.grid(row=0, column=1) / name.place(x=1, y=2) for a widget in the tree. .pack() is left as code."""
    if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute)
            and isinstance(st.value.func.value, ast.Name) and st.value.func.value.id in known):
        return False
    manager, name, call = st.value.func.attr, st.value.func.value.id, st.value
    spec = pack.layouts.get(manager)
    if spec is None or spec.get("child_only") or call.args or any(k.arg is None for k in call.keywords):
        return False
    node = tree.find(known[name])
    if node is None or node is tree.root or node["layout"].get("manager"):
        return False
    if manager not in pack.layouts_for(tree.parent_of(node["id"])["type"]):
        return False
    by_arg = {p["arg"]: p for p in spec["props"]}
    values, extra = {"manager": manager}, {}
    for kw in call.keywords:
        p = by_arg.get(kw.arg)
        src = _src(kw.value)
        ok, val = _literal(src)
        if p is not None and ok:
            values[p["key"]] = _fit(p["kind"], val)
        else:
            extra[kw.arg] = src
    if extra:
        values["extra"] = extra
    node["layout"] = values
    return True
