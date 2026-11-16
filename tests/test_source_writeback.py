"""Pure test: source_writeback (source-first phase 2) - edits go back into only the nodes that changed."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portable
import source_writeback as sw

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def cut_chunks(text):
    cut = portable.split_top_level(text)
    return [(i, c) for i, (_n, c) in zip(portable.unique_ids(n for n, _c in cut), cut)]


TEXT = ("import os\n\n\ndef greet(name):\n  print( name )   # odd spacing on purpose\n\n\n"
        "def shout(name):\n    print(name.upper())\n\ngreet('x')\n")
chunks = cut_chunks(TEXT)
check("the file is cut losslessly", sw.join(chunks) == TEXT and len(chunks) >= 3)
baseline = {i: "gen:" + i for i, _c in chunks}


def current(**over):
    return [(i, over.get(i, baseline[i])) for i, _c in chunks]


# ---- nothing edited: byte-exact ----
check("untouched -> the same bytes (odd formatting kept)", sw.join(sw.plan(chunks, baseline, current())) == TEXT)

# ---- one node edited: only it changes ----
new = sw.join(sw.plan(chunks, baseline, current(shout="def shout(name):\n    print(name.lower())\n")))
check("only the edited node is replaced", "lower" in new and "upper" not in new
      and new.startswith(TEXT[:TEXT.index("def shout")]) and new.endswith("\n\ngreet('x')\n"))
check("the odd spacing of other nodes is untouched", "print( name )   # odd spacing on purpose" in new)
check("blank lines after the node are kept", "lower())\n\n" in new)

# ---- an edited node takes on the file's indentation ----
check("indent unit: tabs, 2 spaces, 4 spaces, none", sw.indent_unit("f {\n\tx\n}\n") == "\t"
      and sw.indent_unit("f:\n  x\n    y\n") == "  " and sw.indent_unit("f:\n    x\n") == "    "
      and sw.indent_unit("x = 1\n") is None)
check("generated 4-space code gets tabs", sw.restyle("f {\n    if x {\n        y\n    }\n}\n", "f {\n\tz\n}\n")
      == "f {\n\tif x {\n\t\ty\n\t}\n}\n")
check("or 2 spaces", sw.restyle("f:\n    y\n", "f:\n  z\n") == "f:\n  y\n")
check("4 spaces / no indentation in the original: unchanged", sw.restyle("f:\n    y\n", "f:\n    z\n") == "f:\n    y\n"
      and sw.restyle("f:\n    y\n", "x = 1\n") == "f:\n    y\n")
tabbed = [("t_f", "func f() {\n\tx()\n}\n"), ("t_g", "func g() {\n}\n")]
out = sw.join(sw.plan(tabbed, {"t_f": "a", "t_g": "b"}, [("t_f", "func f() {\n    y()\n}\n"), ("t_g", "b")]))
check("an edited node in a tab-indented file is written with tabs", out == "func f() {\n\ty()\n}\nfunc g() {\n}\n")

# ---- deleted and added nodes ----
gone = [(i, g) for i, g in current() if i != "shout"]
out = sw.join(sw.plan(chunks, baseline, gone))
check("a deleted node is dropped", "shout" not in out and "def greet" in out)
extra = current() + [("fresh", "def fresh():\n    return 1\n")]
out = sw.join(sw.plan(chunks, baseline, extra))
check("a new node is appended after a blank line", out.startswith(TEXT) and out.endswith("\n\ndef fresh():\n    return 1\n"))
check("an empty new node writes nothing", sw.join(sw.plan(chunks, baseline, current() + [("e", "  \n")])) == TEXT)

# ---- a last chunk without a final newline ----
t2 = "def a():\n    pass\n\ndef b():\n    pass"
c2 = cut_chunks(t2)
b2 = {i: "g" + i for i, _c in c2}
out = sw.join(sw.plan(c2, b2, [(i, "g" + i) for i, _c in c2] + [("c", "def c():\n    pass\n")]))
check("a missing final newline never glues lines", "    pass\n\ndef c" in out and out.count("def b()") == 1)

# ---- reading and writing files ----
with tempfile.TemporaryDirectory() as d:
    def put(name, data):
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    s, why = sw.read_source(put("lf.py", b"a = 1\nb = 2\n"))
    check("a normal file reads", s and s.text == "a = 1\nb = 2\n" and s.eol == "\n" and not s.bom)
    s, why = sw.read_source(put("crlf.py", b"a = 1\r\nb = 2\r\n"))
    check("Windows line ends are remembered and read as \\n", s and s.text == "a = 1\nb = 2\n" and s.eol == "\r\n")
    p = put("w.py", b"a = 1\r\nb = 2\r\n")
    sw.write_source(p, "a = 1\nb = 3\n", s)
    check("written back with the same line ends", open(p, "rb").read() == b"a = 1\r\nb = 3\r\n")
    s, why = sw.read_source(put("bom.py", b"\xef\xbb\xbfa = 1\n"))
    check("a BOM is kept", s and s.bom and s.text == "a = 1\n")
    p = put("bom2.py", b"\xef\xbb\xbfa = 1\n")
    sw.write_source(p, "a = 2\n", s)
    check("and written back", open(p, "rb").read() == b"\xef\xbb\xbfa = 2\n")
    s, why = sw.read_source(put("mixed.py", b"a\r\nb\nc\n"))
    check("mixed line ends are refused (writing could not be exact)", s is None and "mixes" in why)
    s, why = sw.read_source(put("cr.py", b"a\rb\r"))
    check("lone carriage returns are refused", s is None)
    s, why = sw.read_source(put("latin.py", "caf\xe9 = 1\n".encode("latin-1")))
    check("a file that is not UTF-8 is refused", s is None and "UTF-8" in why)
    s, why = sw.read_source(os.path.join(d, "missing.py"))
    check("a missing file is refused, not raised", s is None)
    p = put("h.py", b"x\n")
    size, mtime, digest = sw.write_source(p, "yy\n", sw.Source("", "\n", False))
    check("write_source reports what is on disk", size == 3 and digest == sw.hash_file(p)
          and not [n for n in os.listdir(d) if n.endswith(".tmp")])

ch = [("a", "def a():\n    pass\n\n\n"), ("b", "def b():\n    pass\n\n\n"), ("c", "def c():\n    pass\n")]
base = {"a": "A", "b": "B", "c": "C"}
cur = [("a", "A"), ("b", "B"), ("c", "C")]
check("no new order -> same chunks", sw.plan(ch, base, cur) == ch and sw.plan(ch, base, cur, ["a", "b", "c"]) == ch)
moved = sw.join(sw.plan(ch, base, cur, ["c", "a", "b"]))
check("a moved node moves its text, gaps stay alike",
      moved == "def c():\n    pass\n\n\ndef a():\n    pass\n\n\ndef b():\n    pass\n")

import source_rename as sr
code = "def old(x):\n    return x  # old\n\n\nprint('old', old(1), obj.old, f(old=2))\n"
out, n = sr.rename_in_text(code, "old", "new")
check("rename touches the definition and calls, not strings, comments, attributes or keyword names",
      out == "def new(x):\n    return x  # old\n\n\nprint('old', new(1), obj.old, f(old=2))\n" and n == 2)
rc, skipped, applied = sr.apply_renames([("a", "def old():\n    pass\n"), ("b", "old()\n")], {"a": ("old", "new")})
check("apply_renames renames across chunks", rc == [("a", "def new():\n    pass\n"), ("b", "new()\n")] and not skipped
      and applied == [("old", "new")])
rc, skipped, _a = sr.apply_renames([("a", "def old():\n    pass\n"), ("b", "new = 1\n")], {"a": ("old", "new")})
check("a name already in use is refused", skipped and rc[0][1].startswith("def old"))
rc, skipped, _a = sr.apply_renames([("a", "def old():\n    pass\n")], {"a": ("old", "class")})
check("a keyword is refused", skipped)

js = 'function old(a) {\n  // old here\n  return "old" + obj.old + `old ${a}` + old(a);\n}\nconst o = {old: 1, k: old};\n'
out, n = sr.rename_in_text(js, "old", "nu", "javascript")
check("JS: definition, calls and values are renamed; comments, strings, members and object keys are not",
      out == 'function nu(a) {\n  // old here\n  return "old" + obj.old + `old ${a}` + nu(a);\n}\nconst o = {old: 1, k: nu};\n' and n == 3)
rs = "fn old<'a>(x: &'a str) -> char { let c = 'o'; Self::old(x); old(x); c }\n"
out, n = sr.rename_in_text(rs, "old", "nu", "rust")
check("Rust: lifetimes are not strings, paths are members",
      out == "fn nu<'a>(x: &'a str) -> char { let c = 'o'; Self::old(x); nu(x); c }\n" and n == 2)
go = 'func old() {\n\t/* old\n\told */ x := "a\\"old"; old()\n}\n'
out, n = sr.rename_in_text(go, "old", "nu", "go")
check("Go: block comments and escaped quotes", out == 'func nu() {\n\t/* old\n\told */ x := "a\\"old"; nu()\n}\n' and n == 2)
check("declares() sees the declaration line", sr.declares("// c\nfunc old() {}\n", "old", "go")
      and not sr.declares("x := old()\n", "old", "go") and sr.declares("async def old():\n  pass", "old", "python"))
check("a name that is not valid in the language is refused", not sr.valid_name("a-b", "javascript")
      and not sr.valid_name("class", "python") and sr.valid_name("$x1", "javascript"))

check("module names", sr.module_name("pkg/utils.py") == "pkg.utils" and sr.module_name("pkg/__init__.py") == "pkg"
      and sr.module_name("u.py") == "u")
t, n = sr.rename_imports("from utils import old, keep\nold()\nobj.old()\n", "main.py", "utils", "old", "nu")
check("from-import: the import and the bare uses", t == "from utils import nu, keep\nnu()\nobj.old()\n" and n == 2)
t, n = sr.rename_imports("from utils import old as o\no()\n", "main.py", "utils", "old", "nu")
check("an aliased import only changes the imported name", t == "from utils import nu as o\no()\n" and n == 1)
t, n = sr.rename_imports("import utils\nutils.old()\nold()\n", "main.py", "utils", "old", "nu")
check("module import: attribute uses only", t == "import utils\nutils.nu()\nold()\n" and n == 1)
t, n = sr.rename_imports("from . import utils as u\nu.old()\n", "pkg/main.py", "pkg.utils", "old", "nu")
check("relative imports are resolved", t == "from . import utils as u\nu.nu()\n" and n == 1)
t, n = sr.rename_imports("from .utils import old\nold()\n", "pkg/main.py", "pkg.utils", "old", "nu")
check("relative from-import", n == 2 and "nu()" in t)
t, n = sr.rename_imports("import os\nold()\n", "main.py", "utils", "old", "nu")
check("a file that does not import the module is left alone", n == 0 and t.startswith("import os"))
t, n = sr.rename_imports("from utils import old\nnu = 1\n", "main.py", "utils", "old", "nu")
check("a clash in the importer is refused", t is None)

re_ = sr.rename_elsewhere
t, n = re_("javascript", "import {old, keep} from './lib.js';\nold(); obj.old(); \"old\";\n", "app.js", "lib.js", "old", "nu")
check("JS named import and bare uses", t == "import {nu, keep} from './lib.js';\nnu(); obj.old(); \"old\";\n" and n == 2)
t, n = re_("javascript", "import {old as o} from './lib.js';\no();\n", "app.js", "lib.js", "old", "nu")
check("JS aliased import: only the imported name", t == "import {nu as o} from './lib.js';\no();\n")
t, n = re_("javascript", "import * as L from './lib';\nL.old(); old();\n", "app.js", "lib.js", "old", "nu")
check("JS namespace import: member uses only", t == "import * as L from './lib';\nL.nu(); old();\n")
t, n = re_("javascript", "const {old} = require('../lib');\nold();\n", "sub/app.js", "lib.js", "old", "nu")
check("JS require with a relative path", t == "const {nu} = require('../lib');\nnu();\n")
t, n = re_("javascript", "import {old} from 'other';\nold();\n", "app.js", "lib.js", "old", "nu")
check("JS: another module's name is left alone", n == 0)
t, n = re_("go", "package m\nfunc f() { old() }\n", "m/b.go", "m/a.go", "old", "nu")
check("Go: same directory is the same package", t == "package m\nfunc f() { nu() }\n")
t, n = re_("go", 'package x\nimport "ex.com/p/util"\nfunc f() { util.Old(); Old() }\n', "x/b.go", "util/a.go", "Old", "New")
check("Go: other package by import path, qualified uses only", t == 'package x\nimport "ex.com/p/util"\nfunc f() { util.New(); Old() }\n')
t, n = re_("rust", "use crate::lib::old;\nfn f() { old(); lib::old(); }\n", "main.rs", "lib.rs", "old", "nu")
check("Rust: module name is the file stem (lib.rs is the crate root, so nothing)", n == 0)
t, n = re_("rust", "use crate::util::old;\nfn f() { old(); util::old(); }\n", "main.rs", "util.rs", "old", "nu")
check("Rust: use path, bare and qualified uses", t == "use crate::util::nu;\nfn f() { nu(); util::nu(); }\n")
t, n = re_("java", "class B { void f() { Util.old(); x.old(); } }\n", "B.java", "Util.java", "old", "nu")
check("Java: Class.method uses", t == "class B { void f() { Util.nu(); x.old(); } }\n")
t, n = re_("csharp", "using static N.Util;\nclass B { void f() { old(); } }\n", "B.cs", "Util.cs", "old", "nu")
check("C#: using static makes bare uses", t == "using static N.Util;\nclass B { void f() { nu(); } }\n")
t, n = re_("c", '#include "util.h"\nint main() { old(); }\n', "main.c", "util.c", "old", "nu")
check("C: files that include the header", t == '#include "util.h"\nint main() { nu(); }\n')
t, n = re_("c", "int old(void);\n", "util.h", "util.c", "old", "nu")
check("C: the header of the same name", t == "int nu(void);\n")
t, n = re_("c", "int main() { old(); }\n", "main.c", "util.c", "old", "nu")
check("C: a file that does not include it is left alone", n == 0)
t, n = re_("javascript", "import {old} from './lib.js';\nconst nu = 1;\n", "app.js", "lib.js", "old", "nu")
check("a clash is refused", t is None)

print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
sys.exit(1 if FAILURES else 0)
