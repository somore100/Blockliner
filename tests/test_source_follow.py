"""Pure test: snapshot / diff / carry_layout of source_follow (source-first phase 1)."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import source_follow

FAILURES = []


def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


EXT = {".py": "python", ".js": "javascript"}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


with tempfile.TemporaryDirectory() as d:
    write(os.path.join(d, "a.py"), "x = 1\n")
    write(os.path.join(d, "pkg", "b.py"), "def f():\n    pass\n")
    write(os.path.join(d, "notes.txt"), "not code")
    s1 = source_follow.snapshot(d, EXT)
    check("source files are found, other types are not", sorted(s1) == ["a.py", "pkg/b.py"])
    check("each has a hash and its language", all(v["hash"] and v["language"] == "python" for v in s1.values()))

    s2 = source_follow.snapshot(d, EXT, previous=s1)
    check("nothing changed -> empty diff", source_follow.diff(s1, s2) == ([], [], []))

    write(os.path.join(d, "a.py"), "x = 2\n")
    write(os.path.join(d, "c.js"), "let y = 1;\n")
    os.remove(os.path.join(d, "pkg", "b.py"))
    s3 = source_follow.snapshot(d, EXT, previous=s2)
    check("added, changed and removed are told apart", source_follow.diff(s2, s3) == (["c.js"], ["a.py"], ["pkg/b.py"]))

    st = os.stat(os.path.join(d, "c.js"))
    os.utime(os.path.join(d, "c.js"), ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    s4 = source_follow.snapshot(d, EXT, previous=s3)
    check("only touched (same content) is not a change", source_follow.diff(s3, s4) == ([], [], []))

    seen = []
    orig = source_follow._hash
    source_follow._hash = lambda p: (seen.append(p), orig(p))[1]
    source_follow.snapshot(d, EXT, previous=s4)
    source_follow._hash = orig
    check("files with the same size and time are not read again", seen == [])

old = [{"id": "main", "name": "main", "canvas_x": 400, "canvas_y": 90, "child_nodes": []},
       {"id": "helper", "name": "helper", "canvas_x": 10, "canvas_y": 20, "child_nodes": []}]
new = [{"id": "helper", "name": "helper", "canvas_x": 0, "canvas_y": 0, "_auto_pos": True, "child_nodes": []},
       {"id": "renamed_id", "name": "main", "canvas_x": 0, "canvas_y": 0, "child_nodes": []},
       {"id": "fresh", "name": "fresh", "canvas_x": 700, "canvas_y": 700, "child_nodes": []}]
n = source_follow.carry_layout(old, new)
check("positions follow the node by id, then by name", n == 2 and (new[0]["canvas_x"], new[0]["canvas_y"]) == (10, 20)
      and (new[1]["canvas_x"], new[1]["canvas_y"]) == (400, 90))
check("a new node keeps its own place", (new[2]["canvas_x"], new[2]["canvas_y"]) == (700, 700))
check("a carried position is no longer 'auto'", "_auto_pos" not in new[0])

print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
sys.exit(1 if FAILURES else 0)
