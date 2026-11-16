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

code = "def old(x):\n    return x  # old\n\n\nprint('old', old(1), obj.old, f(old=2))\n"
out, n = sw.rename_python(code, "old", "new")
check("rename touches the definition and calls, not strings, comments, attributes or keyword names",
      out == "def new(x):\n    return x  # old\n\n\nprint('old', new(1), obj.old, f(old=2))\n" and n == 2)
rc, skipped = sw.apply_renames([("a", "def old():\n    pass\n"), ("b", "old()\n")], {"a": ("old", "new")})
check("apply_renames renames across chunks", rc == [("a", "def new():\n    pass\n"), ("b", "new()\n")] and not skipped)
rc, skipped = sw.apply_renames([("a", "def old():\n    pass\n"), ("b", "new = 1\n")], {"a": ("old", "new")})
check("a name already in use is refused", skipped and rc[0][1].startswith("def old"))
rc, skipped = sw.apply_renames([("a", "def old():\n    pass\n")], {"a": ("old", "class")})
check("a keyword is refused", skipped)

print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
sys.exit(1 if FAILURES else 0)
