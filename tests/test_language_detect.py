"""Guessing a language from code (pure)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import language_detect as L

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

SAMPLES = {
 "python": ["import os\n\ndef greet(name):\n    print(f'hi {name}')\n    return None\n", "class A:\n    def f(self):\n        if self.x:\n            pass\n        elif self.y:\n            pass\n",
            "for i in range(10):\n    print(i)\nwith open('f') as fh:\n    data = fh.read()\n"],
 "javascript": ["const x = 3;\nfunction add(a, b) {\n  return a + b;\n}\nconsole.log(add(1, 2));\n", "const fs = require('fs');\nmodule.exports = { a: 1 };\n",
                "let f = async (a) => { await g(a); };\nif (a === b) { document.title = 'x'; }\n"],
 "java": ["public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"hi\");\n    }\n}\n", "import java.util.*;\n@Override\npublic String toString() { return \"x\"; }\n"],
 "csharp": ["using System;\nnamespace App {\n  class P {\n    static void Main(string[] a) {\n      Console.WriteLine(\"hi\");\n    }\n  }\n}\n", "public int Age { get; set; }\nforeach (var x in items) { Console.WriteLine(x); }\n"],
 "cpp": ["#include <iostream>\nusing namespace std;\nint main() {\n    cout << \"hi\" << endl;\n    return 0;\n}\n", "std::vector<int> v;\nfor (auto x : v) { std::cout << x; }\n"],
 "c": ["#include <stdio.h>\nint main(void) {\n    printf(\"hi\\n\");\n    return 0;\n}\n", "#include <stdlib.h>\nchar *p = malloc(10);\nfree(p);\nstruct node { int v; };\n"],
 "go": ["package main\n\nimport \"fmt\"\n\nfunc main() {\n    x := 3\n    fmt.Println(x)\n}\n", "func (s *Server) Start() error {\n    if err != nil {\n        return err\n    }\n}\n"],
 "rust": ["use std::io;\n\nfn main() {\n    let mut x = 3;\n    println!(\"{}\", x);\n}\n", "pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\nimpl Foo { fn new() -> Self { Foo {} } }\n"],
 "html": ["<!DOCTYPE html>\n<html>\n<body>\n<div><p>hi</p></div>\n</body>\n</html>\n", "<div class=\"a\">\n  <ul><li>one</li><li>two</li></ul>\n</div>\n"],
}

def main():
    for lang, snippets in SAMPLES.items():
        for i, s in enumerate(snippets):
            g = L.detect(s)
            check(f"{lang} #{i + 1} is recognised ({g.language}, {g.confidence})", g.language == lang)
    check("plain words are not guessed", L.detect("hello there, this is just a sentence.").language is None)
    check("a bare assignment is not guessed", L.detect("x = 1\ny = 2\nz = x + y\n").language is None)
    check("empty text is not guessed", L.detect("").language is None and L.detect("   ").language is None)
    check("the extension is only a hint", L.detect("x = 1\ny = 2\nz = 3\n", ".py", {".py": "python"}).language is None)
    check("a hint settles a close call", L.detect("int x = 3;\nx++;\nreturn x;\n", ".c", {".c": "c"}).language in (None, "c"))
    g = L.detect("#include <stdio.h>\nint main(void) {\n    printf(\"a\");\n}\n", ".cpp", {".cpp": "cpp"})
    check("the code wins over a wrong extension", g.language == "c")
    check("ranking is returned best first", L.detect(SAMPLES["go"][0]).ranking[0][0] == "go")
    print("ALL OK" if not FAILURES else f"FAILURES: {FAILURES}")
    sys.exit(1 if FAILURES else 0)
main()
