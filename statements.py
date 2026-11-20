"""Where a statement ends (pure, no Tk): used by the importer to keep a multi-line statement as one block."""


def statement_end(lines, i):
    """Index of the last physical line of the statement that starts at lines[i] (Python-style source): it goes on while a
    bracket is open, inside a triple-quoted string, or after a trailing backslash. A statement that ends in ':' is a
    compound header and is never grouped (its body is parsed on its own). Returns i for a one-line statement."""
    depth, triple, j = 0, None, i
    while j < len(lines):
        text, k, cont = lines[j], 0, False
        single = None
        while k < len(text):
            ch = text[k]
            if triple:
                if text.startswith(triple, k):
                    k += 3
                    triple = None
                    continue
                if ch == "\\":
                    k += 1
            elif single:
                if ch == "\\":
                    k += 1
                elif ch == single:
                    single = None
            elif ch == "#":
                break
            elif ch in "'\"":
                if text.startswith(ch * 3, k):
                    triple = ch * 3
                    k += 3
                    continue
                single = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            k += 1
        code = text.split("#", 1)[0].rstrip() if not triple and not single else text
        if code.endswith("\\") and not triple:
            cont = True
        if triple or depth > 0 or cont:
            j += 1
            continue
        break
    j = min(j, len(lines) - 1)
    if j > i and lines[j].split("#", 1)[0].rstrip().endswith(":") and not triple:
        return i                                   # a compound header spread over lines: keep the line-by-line behaviour
    return j
