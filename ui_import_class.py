"""Turn a class-based tkinter program into the flat shape ui_import_reader reads (pure, no Tk).

    class App(tk.Tk):                          root = tk.Tk()
        def __init__(self):                    display = tk.Label(root, ...)
            super().__init__()        ->       def press(n): ...
            self.display = tk.Label(self)      root.mainloop()
        def press(self, n): ...
    App().mainloop()

Two shapes are understood: the class IS the window (`class App(tk.Tk)`), or it receives it (`class App: def __init__(self,
master)` with `root = tk.Tk(); App(root)` below). `self.x` becomes the plain name `x`, methods become functions (their
`self` parameter dropped, a `global` line added where they assign), and a method that only builds widgets and is called
from __init__ is written out in place. It is a rewrite of the program's text, so it refuses (and says why) whenever it
could change what the program does: class attributes, decorators, inheritance from anything but Tk, a name used both as
`self.x` and as a local variable, an instance used after it is made, more than one window class.
"""
import ast
import copy

ROOT_CLASSES = {"Tk", "CTk"}


class Refuse(Exception):
    pass


def _name(node):
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)


def _is_self(node, self_name):
    return isinstance(node, ast.Name) and node.id == self_name


def flatten(source):
    """(new source, notes) when a window class was rewritten; (None, [reason]) when one was found but can't be, or
    (None, []) when there is no such class."""
    try:
        module = ast.parse(source)
    except SyntaxError:
        return None, []
    classes = [st for st in module.body if isinstance(st, ast.ClassDef) and any(
        isinstance(m, ast.FunctionDef) and m.name == "__init__" for m in st.body)]
    if not classes:
        return None, []
    reasons = []
    for cls in classes:
        try:
            return _flatten_class(module, cls)
        except Refuse as e:
            reasons.append(f"class {cls.name}: {e}")
    return None, reasons


def _flatten_class(module, cls):
    init = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == "__init__")
    bases = [_name(b) for b in cls.bases]
    mode_a = bases == [b for b in bases if b in ROOT_CLASSES] and len(bases) == 1
    if not mode_a and bases not in ([], ["object"]):
        raise Refuse("it inherits from something other than Tk")
    if not init.args.args or len(init.args.args) > (1 if mode_a else 2) or init.args.vararg or init.args.kwarg \
            or init.args.kwonlyargs or init.args.defaults:
        raise Refuse("__init__ must be __init__(self)" + ("" if mode_a else " or __init__(self, master)"))
    self_name = init.args.args[0].arg
    param = None if mode_a else init.args.args[1].arg
    methods = {}
    for item in cls.body:
        if item is init:
            continue
        if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            continue                                              # the docstring
        if not isinstance(item, ast.FunctionDef) or item.decorator_list or not item.args.args \
                or item.args.args[0].arg != self_name:
            raise Refuse("it has class attributes, decorators or a method without self, which the designer can't keep")
        methods[item.name] = item

    # where the instance is made: that is where the window's code goes
    inst_i, inst_kind, app_var, root_var = None, None, None, None
    for i, st in enumerate(module.body):
        call = st.value if isinstance(st, (ast.Assign, ast.Expr)) else None
        if mode_a:
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                    and _is_call_of(st.value, cls.name) and not st.value.args:
                inst_i, inst_kind, app_var = i, "assign", st.targets[0].id
                break
            if isinstance(st, ast.Expr) and isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) \
                    and call.func.attr == "mainloop" and _is_call_of(call.func.value, cls.name):
                inst_i, inst_kind = i, "chain"
                break
        else:
            if isinstance(call, ast.Call) and _is_call_of(call, cls.name) and len(call.args) == 1 \
                    and isinstance(call.args[0], ast.Name):
                inst_i, inst_kind, root_var = i, "bare", call.args[0].id
                app_var = st.targets[0].id if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) else None
                break
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) \
                    and isinstance(st.value, ast.Call) and _is_call_of(st.value, cls.name) and len(st.value.args) == 1 \
                    and isinstance(st.value.args[0], ast.Name):
                inst_i, inst_kind, app_var, root_var = i, "assign", st.targets[0].id, st.value.args[0].id
                break
    if inst_i is None:
        raise Refuse("I can't find where the window is made (" + (f"{cls.name}()" if mode_a else f"{cls.name}(root)") + ")")

    used = {n.id for n in ast.walk(module) if isinstance(n, ast.Name)}
    window = root_var if not mode_a else ("root" if "root" not in used else "window")

    # attributes (self.x = ...) and what each name means
    attrs, aliases = set(), set()
    for fn in [init] + list(methods.values()):
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and _is_self(n.value, self_name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                attrs.add(n.attr)
    if not mode_a:
        for st in init.body:                                     # self.root = root: another name for the window
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Attribute) \
                    and _is_self(st.targets[0].value, self_name) and isinstance(st.value, ast.Name) and st.value.id == param:
                aliases.add(st.targets[0].attr)
    hoisted = (attrs | set(methods)) - aliases
    module_names = {n for st in module.body if st is not cls for n in _defined(st)}
    clash = hoisted & (module_names - ({app_var} if app_var else set()))
    if clash:
        raise Refuse(f"{sorted(clash)[0]!r} is also a name outside the class")
    for name, fn in methods.items():
        both = hoisted & _locals(fn, skip=(self_name,))
        if both:
            raise Refuse(f"'{sorted(both)[0]}' is used both as self.{sorted(both)[0]} and as a local name in {name}()")

    rewriter = _Rewriter(self_name, window, hoisted, aliases, mode_a, param)
    init_stmts = []
    for st in init.body:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) \
                and st.value.func.attr == "__init__":
            if not mode_a:
                raise Refuse("it calls a base __init__")
            continue                                             # super().__init__() / tk.Tk.__init__(self)
        if not mode_a and isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Attribute) \
                and _is_self(st.targets[0].value, self_name) and st.targets[0].attr in aliases:
            continue
        init_stmts.append(rewriter.visit(copy.deepcopy(st)))
    new_methods = {}
    for name, fn in methods.items():
        f = copy.deepcopy(fn)
        f.args.args = f.args.args[1:]
        f = rewriter.visit(f)
        new_methods[name] = f

    # a method called as a bare statement from __init__ that takes no arguments is written out in place
    inlined = set()

    def expand(stmts, depth=0):
        out = []
        for st in stmts:
            call = st.value if isinstance(st, ast.Expr) else None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in new_methods \
                    and not call.args and not call.keywords and not new_methods[call.func.id].args.args \
                    and depth < 4 and not any(isinstance(n, ast.Return) for n in ast.walk(new_methods[call.func.id])):
                inlined.add(call.func.id)
                out.extend(expand(new_methods[call.func.id].body, depth + 1))
            else:
                out.append(st)
        return out
    init_stmts = expand(init_stmts)

    kept = []
    for name, f in new_methods.items():
        if name in inlined and not _called(name, [m for n, m in new_methods.items() if n != name and n not in inlined] + init_stmts, init_stmts):
            continue
        assigned = sorted({n.id for n in ast.walk(f) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
                           and n.id in hoisted and n.id not in _locals_args(f)})
        if assigned:
            f.body.insert(0, ast.Global(names=assigned))
        kept.append(f)

    base_expr = cls.bases[0] if mode_a else None
    out_body = []
    for i, st in enumerate(module.body):
        if st is cls:
            out_body.extend(kept)
        elif i == inst_i:
            if mode_a:
                out_body.append(ast.Assign(targets=[ast.Name(window, ast.Store())],
                                           value=ast.Call(func=copy.deepcopy(base_expr), args=[], keywords=[])))
            out_body.extend(init_stmts)
            if inst_kind == "chain":
                out_body.append(ast.Expr(ast.Call(ast.Attribute(ast.Name(window, ast.Load()), "mainloop", ast.Load()), [], [])))
        elif mode_a and app_var and isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) \
                and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "mainloop" \
                and _is_name(st.value.func.value, app_var):
            out_body.append(ast.Expr(ast.Call(ast.Attribute(ast.Name(window, ast.Load()), "mainloop", ast.Load()), [], [])))
        else:
            if app_var and i > inst_i and any(isinstance(n, ast.Name) and n.id == app_var for n in ast.walk(st)):
                raise Refuse(f"the instance '{app_var}' is used after it is made")
            out_body.append(st)
    new = ast.fix_missing_locations(ast.Module(body=out_body, type_ignores=[]))
    note = (f"The class {cls.name} was rewritten as plain functions and variables (self.x became x); "
            "the window's code runs where the class was used.")
    return ast.unparse(new) + "\n", [note]


def _is_name(node, name):
    return isinstance(node, ast.Name) and node.id == name


def _is_call_of(node, class_name):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == class_name


def _defined(st):
    if isinstance(st, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
        return {st.name}
    return {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def _locals_args(fn):
    return {a.arg for a in fn.args.args}


def _locals(fn, skip=()):
    names = {a.arg for a in fn.args.args if a.arg not in skip}
    names |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    return names


def _called(name, others, init_stmts):
    for node in others:
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id == name:
                return True
    return False


class _Rewriter(ast.NodeTransformer):
    def __init__(self, self_name, window, hoisted, aliases, mode_a, param):
        self.self_name, self.window, self.hoisted = self_name, window, hoisted
        self.aliases, self.mode_a, self.param = aliases, mode_a, param

    def visit_Attribute(self, node):
        if _is_self(node.value, self.self_name):
            if node.attr in self.aliases:
                return ast.copy_location(ast.Name(self.window, node.ctx), node)
            if node.attr in self.hoisted:
                return ast.copy_location(ast.Name(node.attr, node.ctx), node)
            if self.mode_a:                                      # self.title(...), self.winfo_width(): the window's own
                return ast.copy_location(ast.Attribute(ast.Name(self.window, ast.Load()), node.attr, node.ctx), node)
            raise Refuse(f"self.{node.attr} is not something the designer can follow")
        return self.generic_visit(node)

    def visit_Name(self, node):
        if node.id == self.self_name:
            if self.mode_a:
                return ast.copy_location(ast.Name(self.window, node.ctx), node)
            raise Refuse("self is used on its own (passed on)")
        if self.param is not None and node.id == self.param:
            return ast.copy_location(ast.Name(self.window, node.ctx), node)
        return node
