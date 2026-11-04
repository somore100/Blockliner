"""Whole-text language checks (pure, no Tk)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import language_checks as LC, line_check

fails = []
def check(name, cond):
    if not cond:
        fails.append(name)

LANGS = os.path.join(HERE, "..", "languages")
def rules(lang): return LC.load_rules(os.path.join(LANGS, lang, "checks.json"))
def run(lang, text): return LC.check_text(text.split("\n"), rules(lang))
def msgs(found): return " | ".join(c.message for c in found.values())

for lang in ("c", "cpp", "java", "csharp", "go", "rust", "javascript"):
    check(f"{lang} has rules", bool(rules(lang)))
check("python has none (indentation language)", rules("python") == {})
check("a missing or damaged file is no rules", LC.load_rules("/nonexistent") == {} and LC.check_text(["x"], {}) == {})

# ---- brackets
good = 'int main() {\n  if (x[1] > 2) { puts("}"); } // )\n  /* ( */\n  return 0;\n}'
check("balanced code, brackets inside strings/comments ignored", run("c", good) == {})
r = run("c", "int main() {\n  foo(1;\n}")
check("a mismatched closer is reported on its line", 2 in r or 3 in r)
r = run("c", "void f() {\n  g();\n")
check("an unclosed brace is reported on the line it opens", list(r) == [1] and "never closed" in r[1].message)
r = run("c", "x = 1);\n")
check("a closer with no opener", list(r) == [1] and "no matching" in r[1].message)
check("every finding is a WARN check", all(c.state == line_check.WARN for c in r.values()))
r = run("javascript", 'let s = "abc;\nlet t = 1;')
check("an open string is reported", list(r) == [1] and "never closed" in r[1].message)
check("a template literal may span lines", run("javascript", "let s = `a\nb ( c`;\nlet t = 1;") == {})
check("block comments span lines", run("c", "/* open (\n still ( */\nint x;") == {})
check("escaped quotes do not end a string", run("c", 'char *s = "a\\"(";') == {})

# ---- pairs (C / C++)
r = run("c", "char *p = malloc(10);\nuse(p);")
check("malloc without free", list(r) == [1] and "free(p)" in r[1].message)
check("malloc with free is fine", run("c", "char *p = (char*)malloc(10);\nfree(p);") == {})
check("a cast before malloc still pairs", run("c", "int *a = (int *) calloc(4, 4);\nfree( a );") == {})
r = run("c", "FILE *f = fopen(\"a\", \"r\");\nread(f);")
check("fopen without fclose", list(r) == [1] and "fclose(f)" in r[1].message)
check("fopen with fclose is fine", run("c", 'FILE *f = fopen("a","r");\nfclose(f);') == {})
check("free in a comment does not count", list(run("c", "char *p = malloc(1);\n// free(p);")) == [1])
r = run("cpp", "int *a = new int[3];\nint *b = new int(5);\ndelete b;")
check("new[] without delete[] (and new with delete is fine)", list(r) == [1] and "delete[]" in r[1].message)
check("C++ delete[] pairs new[]", run("cpp", "int *a = new int[3];\ndelete[] a;") == {})
check("java has no pair rules", run("java", "Object o = new Object();") == {})

# ---- semicolons (JavaScript)
js = "let a = 1;\nlet b = 2\nconsole.log(a);\nfoo(b);\n"
r = run("javascript", js)
check("a missing semicolon in a file that uses them", list(r) == [2] and "';'" in r[2].message)
check("a file without semicolons is left alone", run("javascript", "let a = 1\nlet b = 2\nfoo(a)\nbar(b)\n") == {})
ok = "function f(a) {\n  return a +\n    1;\n}\nconst o = {\n  x: 1,\n  y: 2\n};\nif (a) {\n  b();\n} else {\n  c();\n}\n[1,2]\n  .map(f);\nlet z = 1;\n"
check("braces, continued expressions and chains are not flagged", run("javascript", ok) == {})
check("two problems on one line are both kept", len(run("c", "x = malloc(2);)\n")[1].message.split("\n")) == 2)

print("ALL OK" if not fails else f"FAILURES: {fails}")
