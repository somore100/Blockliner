"""Read a HAND-WRITTEN Kivy program (Python, `add_widget` style) into a designer tree (pure, no Tk).

    class CalcApp(App):                                   root = RelativeLayout()   (the window)
        def build(self):                                  grid = GridLayout(cols=3)
            grid = GridLayout(cols=3)           ->        root.add_widget(grid) ... (what the Kivy pack writes)
            grid.add_widget(Button(text="1", on_press=self.press))
            return grid
        def press(self, instance): ...                    def press(instance): ...   (a plain function)
    CalcApp().run()

Same rules as ui_import_reader: what the pack understands becomes widgets, props, layout and event links; any option
the pack has no prop for stays as the widget's `extra` option as written; statements the designer can't place stay as
code inside the window's function; everything else (imports, helper functions, the methods of the App class written
out as plain functions) stays outside as ordinary code. `.kv` files / `Builder.load_string` are not read.

Only the plain shape is taken: class members must be build(), a `title`, and ordinary methods used as handlers; a
method may use `self.name` only for names set in the class itself. Anything else is refused with the reason.
"""
import ast
import copy
import re
import textwrap

import ui_import_class
from ui_tree import UITree

LAYOUT_ROOTS = {"RelativeLayout", "FloatLayout"}
GRID, BOX = "GridLayout", "BoxLayout"
_BIND_RE = re.compile(r"bind\((\w+)=\{handler\}\)")


def _class_map(pack):
    """{Kivy class name: widget type}: from the pack's own templates (TextInput is decided by `multiline`)."""
    out = {}
    for wtype, w in pack.widgets.items():
        if not w["code"] or wtype in pack.root_types:
            continue
        m = re.match(r"\{name\}\s*=\s*(\w+)\(", w["code"][0])
        if m and m.group(1) != "TextInput":
            out.setdefault(m.group(1), wtype)
    if "frame" in pack.widgets:
        out.setdefault("FloatLayout", "frame")
    return out


def _call_class(node):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def _is_self(node, name):
    return isinstance(node, ast.Name) and node.id == name


class _Spec:
    def __init__(self, name, cls, call):
        self.name, self.cls, self.call = name, cls, call
        self.children, self.attached = [], False


def read(source, pack, result_type):
    res = result_type()
    try:
        module = ast.parse(source)
    except SyntaxError as e:
        res.problems.append(f"the code has a syntax error (line {e.lineno})")
        return res
    if "Builder" in source or ".kv" in source:
        res.problems.append("this program uses a .kv file or Builder.load_string, which isn't read yet (only widgets made in Python)")
        return res
    classes = _class_map(pack)
    app = next((st for st in module.body if isinstance(st, ast.ClassDef)
                and any((b.id if isinstance(b, ast.Name) else getattr(b, "attr", None)) == "App" for b in st.bases)
                and any(isinstance(m, ast.FunctionDef) and m.name == "build" for m in st.body)), None)
    if app is None:
        res.problems.append("no window was found (a class App subclass with a build(self) method that returns the layout)")
        return res
    try:
        return _read_app(source, module, app, pack, classes, res)
    except ui_import_class.Refuse as e:
        res.problems.append(f"class {app.name}: {e}")
        return res


def _read_app(source, module, app, pack, classes, res):
    build = next(m for m in app.body if isinstance(m, ast.FunctionDef) and m.name == "build")
    if len(build.args.args) != 1 or build.args.vararg or build.args.kwarg:
        raise ui_import_class.Refuse("build must be build(self)")
    self_name = build.args.args[0].arg
    title, methods = None, {}
    for item in app.body:
        if item is build or (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)):
            continue
        if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name) \
                and item.targets[0].id == "title" and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            title = item.value.value
            continue
        if isinstance(item, ast.FunctionDef) and not item.decorator_list and item.args.args and item.args.args[0].arg == self_name \
                and not item.name.startswith("__"):
            methods[item.name] = item
            continue
        raise ui_import_class.Refuse("it has members other than build(), a title and plain methods (on_start, properties, decorators...)")

    # self.title = "..." inside build: the window title
    body = []
    for st in build.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Attribute) \
                and _is_self(st.targets[0].value, self_name) and st.targets[0].attr == "title" \
                and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
            title = st.value.value
        else:
            body.append(st)

    attrs = set()
    for fn in [build] + list(methods.values()):
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and _is_self(n.value, self_name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                attrs.add(n.attr)
    hoisted = attrs | set(methods)
    module_names = {n for st in module.body if st is not app for n in ui_import_class._defined(st)}
    clash = hoisted & module_names
    if clash:
        raise ui_import_class.Refuse(f"{sorted(clash)[0]!r} is also a name outside the class")
    for name, fn in methods.items():
        both = hoisted & ui_import_class._locals(fn, skip=(self_name,))
        if both:
            raise ui_import_class.Refuse(f"'{sorted(both)[0]}' is used both as self.{sorted(both)[0]} and as a local name in {name}()")
    rw = ui_import_class._Rewriter(self_name, "root", hoisted, set(), False, None)
    body = [rw.visit(copy.deepcopy(st)) for st in body]
    funcs = []
    for name, fn in methods.items():
        f = copy.deepcopy(fn)
        f.args.args = f.args.args[1:]
        f = rw.visit(f)
        assigned = sorted({n.id for n in ast.walk(f) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
                           and n.id in hoisted and n.id not in ui_import_class._locals_args(f)})
        if assigned:
            f.body.insert(0, ast.Global(names=assigned))
        funcs.append(ast.fix_missing_locations(f))

    def unparse(st):
        return ast.unparse(ast.fix_missing_locations(st))

    # ---- pass 1: what build() does
    notes = res.report
    specs, order, pre, post = {}, [], [], []
    root_name, links = None, []
    size = None
    seen_widget = False
    ui_names = set()

    def new_spec(name, call):
        cls = _call_class(call)
        if cls in LAYOUT_ROOTS or cls in (GRID, BOX) or cls in classes:
            if cls == "TextInput":
                return None
            return _Spec(name, cls, call)
        if cls == "TextInput":
            return _Spec(name, cls, call)
        return None

    def usable(call):
        return not any(isinstance(a, ast.Starred) for a in call.args) and all(k.arg is not None for k in call.keywords) \
            and not call.args

    for st in body:
        if isinstance(st, ast.Return):
            if isinstance(st.value, ast.Name) and st.value.id in specs:
                root_name = st.value.id
            break
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                and isinstance(st.value, ast.Call) and usable(st.value) and (sp := new_spec(st.targets[0].id, st.value)) \
                and st.targets[0].id not in specs:
            specs[sp.name] = sp
            order.append(sp)
            ui_names.add(sp.name)
            seen_widget = True
            continue
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Attribute) \
                and isinstance(st.targets[0].value, ast.Name) and st.targets[0].value.id == "Window" \
                and st.targets[0].attr == "size":
            try:
                value = ast.literal_eval(st.value)
            except (ValueError, SyntaxError):
                value = None
            if isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value):
                size = value
                continue
        call = st.value if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) else None
        if call is not None and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) \
                and call.func.value.id in specs:
            parent, method = specs[call.func.value.id], call.func.attr
            if method == "add_widget" and len(call.args) == 1 and not call.keywords:
                arg = call.args[0]
                child = None
                if isinstance(arg, ast.Name) and arg.id in specs and not specs[arg.id].attached and specs[arg.id] is not parent:
                    child = specs[arg.id]
                elif isinstance(arg, ast.Call) and usable(arg):
                    child = new_spec(None, arg)
                    if child is not None:
                        order.append(child)
                if child is not None:
                    child.attached = True
                    parent.children.append(child)
                    continue
            if method == "bind" and not call.args and call.keywords and all(
                    k.arg is not None and isinstance(k.value, ast.Name) for k in call.keywords):
                events = _event_keys(pack, specs[call.func.value.id], classes)
                if all(k.arg in events for k in call.keywords):
                    for k in call.keywords:
                        links.append((specs[call.func.value.id], events[k.arg], k.value.id))
                    continue
        (post if seen_widget else pre).append(unparse(st))
        ui_names |= {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        if any(isinstance(n, ast.Name) and n.id in specs for n in ast.walk(st)):
            notes.append(f"kept as code (the designer can't place it): {unparse(st).splitlines()[0][:70]}")

    if root_name is None:
        res.problems.append("build() has to end with  return <layout>  where the layout is made in build() with plain arguments")
        return res
    root = specs[root_name]
    if root.cls not in LAYOUT_ROOTS and root.cls not in (GRID, BOX):
        res.problems.append("build() returns a widget that is not a layout (BoxLayout, GridLayout, RelativeLayout...)")
        return res

    # ---- pass 2: the tree
    root_type = pack.root_types[0]
    props = pack.defaults(root_type)
    if title is not None:
        props["title"] = title
    if size:
        props["width"], props["height"] = size
    wrap = root.cls not in LAYOUT_ROOTS
    tree_root_name = root.name if not wrap else tree_unique(root.name + "_window", [s.name for s in order])
    tree = UITree.new(pack.id, root_type=root_type, root_name=tree_root_name, props=props, is_container=pack.is_container)
    names = {s.name for s in order if s.name}
    count = [0]
    used = {tree_root_name}

    def add(spec, parent_node, parent_spec_type, force_place=False):
        wtype = _wtype(spec, classes)
        w = pack.widget(wtype)
        if w is None:
            notes.append(f"'{spec.name or spec.cls}': there is no {spec.cls} in the Kivy pack")
            return
        kwargs = {k.arg: k.value for k in spec.call.keywords}
        values, extra, layout = {}, {}, {}
        by_arg = {p["arg"]: p for p in w["props"] if not p["inline"]}
        events = _event_keys(pack, spec, classes)
        kwargs.pop("multiline", None) if spec.cls == "TextInput" else None
        in_box = parent_spec_type in (GRID, BOX)
        # fixed sizes
        if in_box:
            for dim, hint in (("width", "size_hint_x"), ("height", "size_hint_y")):
                if dim in kwargs and hint in kwargs and _lit(kwargs[hint]) == (True, None) and _lit(kwargs[dim])[0] \
                        and isinstance(_lit(kwargs[dim])[1], int):
                    layout[dim] = _lit(kwargs.pop(dim))[1]
                    kwargs.pop(hint)
        elif parent_node is not tree.root or force_place:
            ok, sz = _lit(kwargs["size"]) if "size" in kwargs else (False, None)
            if ok and isinstance(sz, tuple) and len(sz) == 2 and all(isinstance(v, int) for v in sz):
                layout["width"], layout["height"] = sz
                kwargs.pop("size")
        elif "size" in kwargs:
            ok, sz = _lit(kwargs["size"])
            if ok and isinstance(sz, tuple) and len(sz) == 2 and all(isinstance(v, int) for v in sz):
                layout["width"], layout["height"] = sz
                kwargs.pop("size")
        for arg, node in kwargs.items():
            if arg in events and isinstance(node, ast.Name):
                links.append((spec, events[arg], node.id))
                continue
            p = by_arg.get(arg)
            if p is not None:
                ok, val = _lit(node)
                if ok and _fits(p, val):
                    values[p["key"]] = val
                    continue
            extra[arg] = ast.unparse(node)
        name = spec.name or tree.unique_name(_base(spec))
        spec.name = name
        if name in used:
            notes.append(f"'{name}' is used for two widgets; the second was renamed")
            name = tree.unique_name(name)
            spec.name = name
        used.add(name)
        try:
            wid = tree.add(parent_node["id"], wtype, name=name, props=values, design={"w": w["default_size"][0], "h": w["default_size"][1]})
        except ValueError:
            notes.append(f"'{name}' sits in something that can't hold widgets")
            return
        node = tree.find(wid)
        node["name"] = name
        if extra:
            node["extra"] = extra
            notes.append(f"'{name}': other options kept as written ({', '.join(extra)})")
        if in_box:
            node["layout"] = dict({"manager": "cell"}, **layout)
        else:
            node["layout"] = dict({"manager": "place", "x": 0, "y": 0}, **layout)
            if "pos" in extra or "pos_hint" in extra:
                notes.append(f"'{name}': its position wasn't carried over (it is placed at 0, 0)")
        for child in spec.children:
            add(child, node, spec.cls)

    if wrap:                                       # a BoxLayout/GridLayout returned: it sits inside the window
        add(root, tree.root, RELATIVE, force_place=True)
        inner = tree.root["children"][0] if tree.root["children"] else None
        if inner is not None:
            inner["layout"] = {"manager": "place", "x": 0, "y": 0, "width": props.get("width", 400), "height": props.get("height", 300)}
            notes.append(f"the window is the {root.cls}; it now sits in a plain window of the same size (it does not resize with it)")
    else:
        rkw = {k.arg: ast.unparse(k.value) for k in root.call.keywords}
        for k, v in rkw.items():
            pre.insert(0, f"{tree_root_name}.{k} = {v}")
        for child in root.children:
            add(child, tree.root, root.cls)
    tree.extra["pre_code"], tree.extra["post_code"] = pre, post
    tree.extra["expose_globals"] = True
    tree._undo, tree._redo = [], []

    # code around the class
    before, after = [], []
    seen_class = False
    for st in module.body:
        if st is app:
            seen_class = True
            before.extend(unparse(f) for f in funcs)
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) \
                and st.value.func.attr == "run" and _call_class(st.value.func.value) == app.name:
            continue                               # CalcApp().run(): the generated program runs the window itself
        (after if seen_class else before).append(textwrap.dedent(ast.get_source_segment(source, st, padded=True) or unparse(st)))
    res.tree = tree
    res.links = [(sp.name, k, h) for sp, k, h in links if sp.name]
    res.before = "\n\n".join(x for x in before if x.strip())
    res.after = "\n\n".join(x for x in after if x.strip())
    res.widgets = sum(1 for _ in tree.walk()) - 1
    if pre or post:
        notes.append(f"{len(pre) + len(post)} statement(s) around the widgets are kept as code inside the window's function")
    notes.insert(0, f"The class {app.name} was rewritten as plain functions and variables (self.x became x); the window's code runs where the class was used.")
    return res


RELATIVE = "RelativeLayout"


def tree_unique(base, taken):
    name = base
    i = 2
    while name in taken:
        name = f"{base}_{i}"
        i += 1
    return name


def _wtype(spec, classes):
    if spec.cls == "TextInput":
        for k in spec.call.keywords:
            if k.arg == "multiline" and _lit(k.value) == (True, False):
                return "entry"
        return "text"
    if spec.cls in LAYOUT_ROOTS:
        return "frame"
    if spec.cls == GRID:
        return "gridframe"
    if spec.cls == BOX:
        return "boxframe"
    return classes[spec.cls]


def _base(spec):
    return _wtype(spec, {}) if spec.cls in LAYOUT_ROOTS or spec.cls in (GRID, BOX, "TextInput") else spec.cls.lower()


def _event_keys(pack, spec, classes):
    """{Kivy event name: the pack's event key} for the widget."""
    w = pack.widget(_wtype(spec, classes)) or {}
    out = {}
    for ev in w.get("events", []):
        m = _BIND_RE.search("\n".join(ev["code"]) if isinstance(ev["code"], list) else ev["code"])
        if m:
            out[m.group(1)] = ev["key"]
    return out


def _lit(node):
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return False, None


def _fits(prop, val):
    kind = prop["kind"]
    if isinstance(val, (set, dict)):
        return False
    if kind == "int":
        return isinstance(val, int) and not isinstance(val, bool)
    if kind == "bool":
        return isinstance(val, bool)
    if kind == "string":
        return isinstance(val, str)
    if kind == "enum":
        return val in (prop.get("options") or [])
    return True
