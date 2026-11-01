"""Free-writing line check (pure, no Tk)."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import line_check as lc

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

def main():
    vocab = lc.language_words("python") | {"my_func"}
    print_rx = re.compile(r"^print\((?P<v>.*)\)$")
    call_rx = re.compile(r"^(?P<n>\w+)\((?P<a>.*)\)$")
    matchers = [print_rx, call_rx, re.compile(r"^(?P<n>\w+) = (?P<v>.+)$")]
    one = lambda line, **kw: lc.analyse_line(line, matchers, vocab, **kw)

    check("a matching line is known", one('print("hi")').state == lc.KNOWN and one('print("hi")').confidence == 1.0)
    check("blank, comment and lone bracket are none", all(one(s).state == lc.NONE for s in ("", "   ", "# note", "}", "  )")))
    c = one("pritn('hi')")
    check("swapped letters is a typo for print", c.state == lc.TYPO and c.word == "pritn" and c.suggestions[0][0] == "print" and c.confidence >= 0.7)
    check("typo is found even though a generic call pattern would match it", c.state == lc.TYPO)
    check("typo position lets the fix be applied", lc.apply_fix("pritn('hi')", c, "print") == "print('hi')")
    check("misspelled statement keyword", one("whlie x < 3:").state == lc.TYPO and one("whlie x < 3:").suggestions[0][0] == "while")
    check("misspelled else", one("esle:").state == lc.TYPO and one("esle:").suggestions[0][0] == "else")
    check("project names count", one("my_fnc(1)").suggestions[0][0] == "my_func")
    check("a library call is unverified, not a typo", one("requests.get(url)").state == lc.UNVERIFIED
          and lc.analyse_line("zzzzzz(1)", [], vocab).state == lc.UNVERIFIED)
    check("a plain call to an unknown name still fits the call block", one("zzzzzz(1)").state == lc.KNOWN)
    check("attributes are never checked", one("obj.pritn(1)").state in (lc.KNOWN, lc.UNVERIFIED))
    check("words inside strings and comments are ignored", one('print("pritn")  # pritn(').state == lc.KNOWN)
    check("assignment targets are not checked", one("pritn = 3").state == lc.KNOWN)
    check("short names are never typos", one("pt(1)").state != lc.TYPO)
    check("ignored words stay quiet", one("pritn('hi')", ignored={"pritn"}).state != lc.TYPO)
    check("a stricter threshold drops weak matches", one("prnt(1)", threshold=0.95).state != lc.TYPO)
    check("closer match scores higher", lc.similarity("pritn", "print") > lc.similarity("prnxx", "print"))
    two = lc.suggest("fooo", {"foo1", "foo2", "bar"}, 0.5)
    check("near ties are all offered", {n for n, _s in two} == {"foo1", "foo2"})
    lines = ["def helper(a, b):", "    return a", "helpr(1, 2)", "x = 5", "pritn(x)"]
    res = lc.analyse_text(lines, matchers, vocab)
    check("names defined in the text are known", res[2].state == lc.TYPO and res[2].suggestions[0][0] == "helper")
    check("defined variables and params are known", {"helper", "a", "b", "x"} <= lc.defined_names(lines))
    check("imports define names", {"np", "path", "os"} <= lc.defined_names(["import numpy as np", "from os import path", "import os.path"]))
    check("words from a pattern skip params and syntax", lc.words_from_pattern(r"^print\((?P<value>.*?)\)$") == {"print"}
          and lc.words_from_pattern(r"^(?P<name>[A-Za-z_]\w*)\.append\((?P<v>.*?)\)$") == {"append"})
    d = lc.describe(c)
    check("bulb text says what is wrong and the fix", '"pritn"' in d and '"print"' in d and "%" in d)
    check("unverified text explains raw code", "raw code" in lc.describe(one("requests.get(url)")))
    print("\nFAILURES:" if FAILURES else "\nALL OK", FAILURES or "")
    sys.exit(1 if FAILURES else 0)

if __name__ == "__main__": main()
