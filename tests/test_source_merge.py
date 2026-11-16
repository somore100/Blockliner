"""Three-way node merge (pure, no Tk)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import source_merge as M

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def fn(name, ret):
    return f"def {name}():\n    return {ret}\n\n\n"


def j(chunks):
    return "".join(t for _i, t in chunks)


BASE = [("a", fn("a", 1)), ("b", fn("b", 2)), ("c", fn("c", 3).rstrip("\n") + "\n")]


def with_(chunks, **changes):
    return [(i, changes.get(i, t)) for i, t in chunks]


# one side only
c, x = M.merge(BASE, with_(BASE, a=fn("a", 11)), BASE)
check("only mine changed: mine is taken", not x and "return 11" in j(c))
c, x = M.merge(BASE, BASE, with_(BASE, b=fn("b", 22)))
check("only theirs changed: theirs is taken", not x and "return 22" in j(c))
c, x = M.merge(BASE, with_(BASE, a=fn("a", 11)), with_(BASE, b=fn("b", 22)))
check("different nodes changed: both changes are kept", not x and "return 11" in j(c) and "return 22" in j(c))
c, x = M.merge(BASE, with_(BASE, a=fn("a", 5)), with_(BASE, a=fn("a", 5)))
check("the same change on both sides is no conflict", not x and j(c).count("return 5") == 1)
c, x = M.merge(BASE, with_(BASE, a=fn("a", 1) + "   "), BASE)
check("trailing blanks do not count as an edit", not x)

# conflict
c, x = M.merge(BASE, with_(BASE, a=fn("a", 11)), with_(BASE, a=fn("a", 99)))
text = j(c)
check("both changed one node differently: a conflict with git-style markers",
      x == ["a"] and "<<<<<<< mine" in text and "=======\n" in text and ">>>>>>> theirs" in text
      and "return 11" in text and "return 99" in text and "def b()" in text)
check("only that node is marked", text.count("<<<<<<<") == 1 and M.has_conflicts(text) and M.count_conflicts(text) == 1)
regions = M.conflict_regions(text)
check("the regions can be read back", len(regions) == 1 and "return 11" in regions[0][0] and "return 99" in regions[0][1])
check("resolve: mine", "return 99" not in M.resolve(text, ["mine"]) and "<<<<" not in M.resolve(text, ["mine"]))
check("resolve: theirs", "return 11" not in M.resolve(text, ["theirs"]))
both = M.resolve(text, ["both"])
check("resolve: both (theirs, then mine)", both.index("return 99") < both.index("return 11") and "====" not in both)
check("a resolved file has no markers", not M.has_conflicts(both))

# add / delete / order
c, x = M.merge(BASE, BASE + [("d", fn("d", 4))], BASE + [("e", fn("e", 5))])
check("a node added on each side: both are kept", not x and "def d()" in j(c) and "def e()" in j(c))
c, x = M.merge(BASE, [n for n in BASE if n[0] != "b"], BASE)
check("deleted on one side, untouched on the other: deleted", not x and "def b()" not in j(c))
c, x = M.merge(BASE, [n for n in BASE if n[0] != "b"], with_(BASE, b=fn("b", 22)))
check("deleted on one side, edited on the other: a conflict", x == ["b"] and "return 22" in j(c))
c, x = M.merge(BASE, BASE, [n for n in BASE if n[0] != "b"])
check("deleted by theirs, untouched by mine: deleted", not x and "def b()" not in j(c))
moved = [BASE[2], BASE[0], BASE[1]]
c, x = M.merge(BASE, moved, BASE)
check("only mine moved nodes: that order is kept", [i for i, _t in c] == ["c", "a", "b"])
c, x = M.merge(BASE, BASE, moved)
check("only theirs moved nodes: that order is kept", [i for i, _t in c] == ["c", "a", "b"])
check("nodes are always separated by a blank line", all(t.endswith("\n\n") for _i, t in c[:-1]))

# renamed outside: the same node by its code
renamed = [("a", BASE[0][1]), ("bee", fn("bee", 2)), BASE[2]]
c, x = M.merge(BASE, with_(BASE, b=fn("b", 2).replace("2", "2  # mine")), renamed)
check("a node renamed on disk is still the same node (alike code)", len([i for i, _t in c]) == 3)

# base/mine/theirs all equal
c, x = M.merge(BASE, BASE, BASE)
check("nothing changed", not x and c == BASE or j(c) == j(BASE))

print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
sys.exit(1 if FAILURES else 0)
