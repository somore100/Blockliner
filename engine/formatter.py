"""
Minimal, semantics-safe line normalizer for code that round-trips
through the code views (text -> blocks -> text).

Deliberately tiny: it only does things that can never change what a
program means -
  * strip trailing whitespace
  * expand LEADING tabs to 4 spaces (mixed tabs/spaces is a real
    TabError in Python, and a mess everywhere else)
It does NOT re-indent, re-wrap or reorder anything: "fixing" odd
indentation (e.g. 3 spaces, or a consistent 2-space file) could change
structure in indentation-sensitive languages.
"""

TAB_WIDTH = 4


def normalize_line(line):
    line = line.rstrip()
    stripped = line.lstrip(" \t")
    indent = line[: len(line) - len(stripped)]
    return indent.replace("\t", " " * TAB_WIDTH) + stripped


def normalize_text(text):
    return "\n".join(normalize_line(l) for l in text.split("\n"))
