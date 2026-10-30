"""Forgiving block search (pure, no Tk)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import palette_search as S

FAILURES = []
def check(label, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {label}")
    if not cond: FAILURES.append(label)

INPUT = {"name": "Input", "description": "Reads a line of text from the keyboard into a variable.", "category": "Basic"}
DIV = {"name": "Div Container", "description": "A generic container element for grouping other elements.", "category": "Basic"}
PRINT = {"name": "Print", "description": "Prints a value to the console.", "category": "Basic"}

def main():
    check("the example: 'reads text' and 'reads a text' both find Input", S.score("reads text", INPUT) > 0 and S.score("reads a text", INPUT) > 0)
    check("filler words are ignored", S.tokens("Reads a line of text") == ["read", "line", "text"])
    check("stemming: reads ~ read, printing ~ prints", S.score("read", INPUT) > 0 and S.score("printing", PRINT) > 0)
    check("prefix: 'cont' finds Container", S.score("cont", DIV) > 0)
    check("a typo is forgiven: 'contanier'", S.score("contanier", DIV) > 0)
    check("every word must match: 'reads video' finds nothing", S.score("reads video", INPUT) == 0)
    check("unrelated words don't match", S.score("keyboard", PRINT) == 0)
    check("empty or only filler matches everything", S.score("", INPUT) > 0 and S.score("the a", PRINT) > 0)
    check("a name hit outranks a description hit", S.score("print", PRINT) > S.score("print", {"name": "Log", "description": "Print later", "category": "x"}))
    check("keywords are searched", S.score("container", {"name": "Div", "description": "", "keywords": "container box"}) > 0)
    check("short words don't fuzz into noise", S.score("xy", INPUT) == 0)
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)

main()
