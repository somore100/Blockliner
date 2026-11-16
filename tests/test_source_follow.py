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

# ---- renamed functions keep their place (match by how alike the code is) ----
import portable

old_chunks = [("main", "def main():\n    greet('x')\n    total = add(1, 2)\n    print(total)\n"),
              ("greet", "def greet(name):\n    print('hello', name)\n    return name\n"),
              ("tiny", "def tiny():\n    pass\n")]
new_chunks = [("main", "def main():\n    greet('x')\n    total = add(1, 2)\n    print(total)\n"),
              ("welcome", "def welcome(name):\n    print('hello', name)\n    return name\n"),
              ("other", "def other():\n    return 42\n")]
ids = portable.unique_ids(n for n, _c in old_chunks)
check("unique_ids keeps names and numbers repeats", ids == ["main", "greet", "tiny"]
      and portable.unique_ids(["a", "a", "a b"]) == ["a", "a_2", "a_b"])
check("chunk_codes uses the marker ids", list(source_follow.chunk_codes(old_chunks)) == ["main", "greet", "tiny"]
      and list(source_follow.chunk_codes([("f", ""), ("f", "")])) == ["f", "f_2"])
old = [{"id": i, "name": i, "canvas_x": 100 * k, "canvas_y": 50 * k, "locked": k == 1, "child_nodes": []}
       for k, i in enumerate(ids)]
new = [{"id": i, "name": i, "canvas_x": 0, "canvas_y": 0, "_auto_pos": True, "child_nodes": []}
       for i in portable.unique_ids(n for n, _c in new_chunks)]
n = source_follow.carry_layout(old, new, source_follow.chunk_codes(old_chunks), source_follow.chunk_codes(new_chunks))
by = {x["id"]: x for x in new}
check("renamed function keeps the old node's place and lock",
      (by["welcome"]["canvas_x"], by["welcome"]["canvas_y"], by["welcome"]["locked"]) == (100, 50, True))
check("an unlike new function does not steal a place", by["other"].get("_auto_pos") and by["other"]["canvas_x"] == 0)
check("matched count is main + the rename", n == 2)
n2 = source_follow.carry_layout(old, [{"id": "welcome", "name": "welcome", "canvas_x": 0, "canvas_y": 0, "child_nodes": []}])
check("without code there is no guessing", n2 == 0)

# two similar functions: each takes its own best partner
a1 = "def a():\n    x = compute(1)\n    return x * 2\n"
b1 = "def b():\n    y = other_thing(9)\n    print(y, y, y)\n    return y\n"
old = [{"id": "a", "name": "a", "canvas_x": 1, "canvas_y": 1, "child_nodes": []},
       {"id": "b", "name": "b", "canvas_x": 2, "canvas_y": 2, "child_nodes": []}]
new = [{"id": "bb", "name": "bb", "canvas_x": 0, "canvas_y": 0, "child_nodes": []},
       {"id": "aa", "name": "aa", "canvas_x": 0, "canvas_y": 0, "child_nodes": []}]
source_follow.carry_layout(old, new, {"a": a1, "b": b1}, {"aa": a1.replace("def a", "def aa"), "bb": b1.replace("def b", "def bb")})
check("each renamed node pairs with its own old node", (new[1]["canvas_x"], new[0]["canvas_x"]) == (1, 2))

# ---- structure splitting in other languages (what follow mode uses) ----
SAMPLES = {
    "javascript": ("const a = 1;\n\nfunction greet(name) {\n  console.log(name);\n}\n\nclass Dog {\n  bark() {\n    return 1;\n  }\n}\n",
                   ["greet", "Dog"]),
    "go": ("package main\n\nimport \"fmt\"\n\nfunc greet(name string) {\n\tfmt.Println(name)\n}\n\nfunc (d Dog) Bark() int {\n\treturn 1\n}\n",
           ["greet", "Bark"]),
    "rust": ("use std::fmt;\n\nfn greet(name: &str) {\n    println!(\"{}\", name);\n}\n\nstruct Dog {\n    age: u32,\n}\n\nimpl Dog {\n    fn bark(&self) -> u32 {\n        1\n    }\n}\n",
             ["greet", "Dog"]),
    "java": ("import java.util.List;\n\npublic class Dog {\n    void bark() {\n        System.out.println(1);\n    }\n}\n\nclass Cat {\n    void meow() {\n    }\n}\n",
             ["Dog", "Cat"]),
    "csharp": ("using System;\n\nclass Dog\n{\n    public void Bark()\n    {\n        Console.WriteLine(1);\n    }\n}\n\nclass Cat\n{\n    public void Meow()\n    {\n    }\n}\n",
               ["Dog", "Cat"]),
    "c": ("#include <stdio.h>\n\nint add(int a, int b) {\n    return a + b;\n}\n\nvoid greet(void) {\n    printf(\"hi\");\n}\n",
          ["add", "greet"]),
    "cpp": ("#include <iostream>\n\nint add(int a, int b) {\n    return a + b;\n}\n\nvoid greet() {\n    std::cout << 1;\n}\n",
            ["add", "greet"]),
}
for lang, (text, want) in SAMPLES.items():
    chunks = portable.split_top_level(text)
    names = [c[0] for c in chunks]
    joined = "".join(c[1] for c in chunks)
    check(f"{lang}: each top-level item is its own node ({names})", all(w in names for w in want) and len(chunks) >= len(want))
    check(f"{lang}: no code is lost or invented by the split",
          [l for l in joined.splitlines() if l.strip()] == [l for l in text.splitlines() if l.strip()])


print("ALL OK" if not FAILURES else f"{len(FAILURES)} FAILED")
sys.exit(1 if FAILURES else 0)
