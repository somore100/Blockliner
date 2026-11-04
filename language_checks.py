"""Whole-text checks per language (pure, no Tk): things a line-by-line look cannot see.

    brackets    ( ) [ ] { } that do not match up, and strings left open
    pairs       something acquired but never released (malloc/free, fopen/fclose)
    semicolons  a line without the ; the rest of the file uses (JavaScript)

The rules are data, in languages/<lang>/checks.json (see load_rules). These are
heuristics: they can warn about code that looks wrong, they cannot prove it is.
Every finding is a line_check.Check with state WARN, so the code panel shows it
with the same gutter marker and bulb as the other checks.
"""
import json
import os
import re

import line_check

_OPEN, _CLOSE = "([{", ")]}"
_PAIR_OF = dict(zip(_CLOSE, _OPEN))
_NEVER_END = tuple("{([,;:") + ("=>", "&&", "||", "+", "-", "*", "/", "=", "?", "<", ">", "&", "|", ".")
_NEVER_START = ("}", ")", "]", ".", ",", "?", ":", "+", "-", "*", "/", "&", "|", "=", "<", ">")
_BLOCK_WORDS = ("if", "for", "while", "else", "function", "class", "switch", "case", "default", "do", "try",
                "catch", "finally", "import", "export", "@")


def load_rules(path):
    """Rules from a checks.json file, or {} when missing or damaged."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _blank(lines, rules):
    """The lines with comments and the insides of strings replaced by spaces
    (same length, so columns stay), [(line, col, quote)] of strings left open,
    and the set of line numbers that end inside a multi-line string or comment."""
    quotes = [q for q in rules.get("quotes", ['"', "'"]) if isinstance(q, str) and len(q) == 1]
    multi = set(rules.get("multiline_quotes", []))
    line_comment = rules.get("line_comment") or None
    block = rules.get("block_comment") or None
    out, open_strings, continued = [], [], set()
    in_block = False
    in_multi = None
    for number, line in enumerate(lines, 1):
        chars = list(line)
        i, n = 0, len(line)
        quote = in_multi
        while i < n:
            if in_block:
                end = line.find(block[1], i)
                stop = n if end < 0 else end + len(block[1])
                for j in range(i, stop):
                    chars[j] = " "
                in_block = end < 0
                i = stop
                continue
            if quote:
                c = line[i]
                if c == "\\":
                    for j in (i, i + 1):
                        if j < n:
                            chars[j] = " "
                    i += 2
                    continue
                if c == quote:
                    quote = None
                    in_multi = None
                else:
                    chars[i] = " "
                i += 1
                continue
            if line_comment and line.startswith(line_comment, i):
                for j in range(i, n):
                    chars[j] = " "
                break
            if block and line.startswith(block[0], i):
                in_block = True
                stop = i + len(block[0])
                for j in range(i, min(stop, n)):
                    chars[j] = " "
                i = stop
                continue
            if line[i] in quotes:
                quote = line[i]
                if quote in multi:
                    in_multi = quote
                i += 1
                continue
            i += 1
        if quote and quote not in multi:
            open_strings.append((number, line.rfind(quote), quote))
        if (quote and quote in multi) or in_block:
            continued.add(number)           # the statement goes on in the next line
        out.append("".join(chars))
    return out, open_strings, continued


def _brackets(blanked):
    """Findings [(line, message)] for brackets that do not pair up."""
    found, stack = [], []
    for number, line in enumerate(blanked, 1):
        for col, c in enumerate(line):
            if c in _OPEN:
                stack.append((c, number))
            elif c in _CLOSE:
                if not stack:
                    found.append((number, f"'{c}' has no matching '{_PAIR_OF[c]}' before it."))
                elif stack[-1][0] != _PAIR_OF[c]:
                    o, at = stack[-1]
                    found.append((number, f"'{c}' closes the '{o}' from line {at}, which does not match."))
                    stack.pop()
                else:
                    stack.pop()
    for o, at in stack:
        found.append((at, f"'{o}' is never closed."))
    return found


def _pairs(blanked, rules):
    found = []
    code = "\n".join(blanked)
    for rule in rules.get("pairs", []):
        try:
            acquire = re.compile(rule["acquire"])
        except (KeyError, re.error, TypeError):
            continue
        release = rule.get("release", "")
        message = rule.get("message", "'{name}' is acquired here but never released.")
        for m in acquire.finditer(code):
            name = m.group(1) if m.groups() else m.group(0)
            try:
                released = re.search(release.replace("{name}", re.escape(name)), code)
            except re.error:
                continue
            if not released:
                line = code.count("\n", 0, m.start()) + 1
                found.append((line, message.replace("{name}", name)))
    return found


def _semicolons(blanked, rules, continued):
    cfg = rules.get("semicolons")
    if not isinstance(cfg, dict):
        return []
    min_share = float(cfg.get("min_share", 0.6))
    code_lines = [(i, s.strip()) for i, s in enumerate(blanked, 1) if s.strip()]
    with_semi, without = 0, []
    for k, (number, text) in enumerate(code_lines):
        if text.endswith(";"):
            with_semi += 1
            continue
        if number in continued:
            continue
        if text.endswith(_NEVER_END) or text.startswith(_NEVER_START) or text.startswith(_BLOCK_WORDS):
            continue
        if text.split(None, 1)[0].rstrip("(") in _BLOCK_WORDS:
            continue
        nxt = code_lines[k + 1][1] if k + 1 < len(code_lines) else ""
        if nxt.startswith(_NEVER_START):
            continue
        without.append(number)
    total = with_semi + len(without)
    if not without or total == 0 or with_semi / total < min_share:
        return []
    msg = "This line has no ';' at the end, while the rest of the file uses them."
    return [(n, msg) for n in without]


def check_text(lines, rules):
    """{line number: Check} of everything suspicious in `lines`."""
    if not rules:
        return {}
    blanked, open_strings, continued = _blank(lines, rules)
    found = []
    if rules.get("brackets", False):
        found += _brackets(blanked)
    for number, col, quote in open_strings:
        found.append((number, f"The string starting with {quote} on this line is never closed."))
    found += _pairs(blanked, rules)
    found += _semicolons(blanked, rules, continued)
    out = {}
    for number, message in sorted(found):
        if number in out:
            if message not in out[number].message:
                out[number].message += "\n" + message
        else:
            out[number] = line_check.Check(line_check.WARN, 0.0, message=message)
    return out
