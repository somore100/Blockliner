"""Source-first, phase 2 (see docs/source-first-mode.md): put an edit made in Blockliner back into the source file,
touching only the nodes that were edited. Pure (no Tk); the only thing here that writes is write_source().

A followed file is cut into chunks (portable.split_top_level; "".join(chunks) is the file). Every chunk is a node.
After an edit, plan() builds the new file text from the old chunks: a node whose generated code is the same as when the
file was read keeps its ORIGINAL text byte for byte (so reading a file and writing it back changes nothing, however it
was formatted); only a node the user really changed is replaced by its newly generated code; a node that is gone is
dropped; a new node is appended at the end."""
import hashlib
import os

import safe_write


class Source:
    """A source file as text: `text` has "\\n" line ends whatever the file used; eol and bom say how to write it back."""
    def __init__(self, text, eol, bom):
        self.text, self.eol, self.bom = text, eol, bom


def decode(raw):
    """Source for the bytes of a file, or (None, reason) when writing it back could not be exact: not valid UTF-8,
    or line ends that are a mix (or a lone carriage return)."""
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "the file is not valid UTF-8"
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    bare_cr = text.count("\r") - crlf
    if bare_cr:
        return None, "the file has old-style (lone carriage return) line ends"
    if crlf and lf:
        return None, "the file mixes Windows and Unix line ends"
    eol = "\r\n" if crlf else "\n"
    return Source(text.replace("\r\n", "\n"), eol, bom), ""


def read_source(path):
    """(Source, "") or (None, reason)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        return None, f"the file cannot be read ({exc.strerror or exc})"
    return decode(raw)


def encode(text, eol="\n", bom=False):
    """The text to write for a file that was read with this eol and bom."""
    if eol != "\n":
        text = text.replace("\n", eol)
    return ("﻿" if bom else "") + text


def hash_file(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def _split_tail(text):
    """(body, tail): the blank lines at the end of a chunk stay with it when the body is replaced."""
    body = text.rstrip(" \t\r\n")
    tail = text[len(body):]
    lines = tail.split("\n")
    # keep the line break that ends the body out of the tail; keep the blank lines after it
    keep = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return body, keep


def indent_unit(text):
    """How the original code indents one level: "\t", or that many spaces as a string; None when it has no indented line."""
    unit = None
    for line in text.split("\n"):
        if not line.strip() or not line[0].isspace():
            continue
        if line[0] == "\t":
            return "\t"
        n = len(line) - len(line.lstrip(" "))
        unit = n if unit is None else min(unit, n)
    return " " * unit if unit else None


def restyle(code, original):
    """Generated code uses 4 spaces per level; give it the file's own indentation (tabs, or 2/8 spaces) so an edited
    node does not look foreign in its file."""
    unit = indent_unit(original)
    if unit is None or unit == "    ":
        return code
    out = []
    for line in code.split("\n"):
        n = len(line) - len(line.lstrip(" "))
        out.append(unit * (n // 4) + " " * (n % 4) + line[n:] if n else line)
    return "\n".join(out)


def plan(chunks, baseline, current, order=None):
    """The file's new chunks.

    chunks   [(id, original text)] in file order
    baseline {id: code generated when the file was read}
    current  [(id, code generated now)] in node order
    order    ids in the order the nodes should have in the file (execution order); None keeps the file's order
    Returns [(id, text)]. Equal to `chunks` when nothing was edited."""
    now = dict(current)
    out = []
    for cid, text in chunks:
        if cid not in now:
            continue                                   # the node was deleted
        gen = now[cid]
        if gen == baseline.get(cid):
            out.append((cid, text))                    # untouched: the original bytes
            continue
        body, keep = _split_tail(text)
        new_body = restyle(gen, body).rstrip("\n")
        out.append((cid, (new_body + "\n" + keep) if new_body else keep))
    out = _reorder(out, order)
    known = {cid for cid, _t in chunks}
    added = [(cid, gen.rstrip("\n") + "\n") for cid, gen in current if cid not in known and gen.strip()]
    if out and added and not out[-1][1].endswith("\n\n"):
        added[0] = (added[0][0], "\n" + added[0][1])      # a new node is set apart from the old end by a blank line
    out += added
    # joining must never glue lines together: a chunk that lost its final newline gets one when something follows
    return [(cid, text + "\n" if text and not text.endswith("\n") and i < len(out) - 1 else text)
            for i, (cid, text) in enumerate(out)]


def _reorder(out, order):
    """`out` [(id, text)] with its nodes in `order` (ids not listed keep their relative place at the end). When the
    order really changes, the blank lines between chunks are made alike: every chunk but the last ends the way the first
    chunk that was followed by a gap did, and the last ends with one line break."""
    if not order or len(out) < 2:
        return out
    rank = {cid: i for i, cid in enumerate(order)}
    new = sorted(out, key=lambda it: rank.get(it[0], len(rank)))          # stable
    if [c for c, _t in new] == [c for c, _t in out]:
        return out
    gap = ""
    for _cid, text in out[:-1]:
        if text.endswith("\n"):
            gap = _split_tail(text)[1]
            break
    fixed = []
    for i, (cid, text) in enumerate(new):
        body, _keep = _split_tail(text)
        if not body:
            fixed.append((cid, text))
        else:
            fixed.append((cid, body + "\n" + (gap if i < len(new) - 1 else "")))
    return fixed


def _python_names(text):
    """[(line, col, name, prev_op, next_op, depth)] for every NAME token, or None when the text does not tokenize."""
    import io
    import keyword
    import tokenize
    out = []
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE)]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    depth = 0
    for i, t in enumerate(toks):
        if t.type == tokenize.OP and t.string in "([{":
            depth += 1
        elif t.type == tokenize.OP and t.string in ")]}":
            depth -= 1
        if t.type == tokenize.NAME and not keyword.iskeyword(t.string):
            prev = toks[i - 1].string if i else ""
            nxt = toks[i + 1].string if i + 1 < len(toks) else ""
            out.append((t.start[0], t.start[1], t.string, prev, nxt, depth))
    return out


def rename_python(text, old, new):
    """`text` with the NAME `old` replaced by `new` (strings and comments are left alone, `x.old` attributes and
    keyword arguments `f(old=1)` are not the function). Returns (text, count) or (None, 0) when it cannot be done."""
    names = _python_names(text)
    if names is None:
        return None, 0
    lines = text.split("\n")
    hits = [(ln, col) for ln, col, name, prev, nxt, depth in names
            if name == old and prev != "." and not (depth > 0 and nxt == "=")]
    for ln, col in sorted(hits, reverse=True):
        line = lines[ln - 1]
        lines[ln - 1] = line[:col] + new + line[col + len(old):]
    return "\n".join(lines), len(hits)


def apply_renames(chunks, renames, original=None):
    """Python only. renames {id: (old name, new name)}: rewrite the definition and every use of the old name in all
    chunks. A rename is skipped (and reported) when the new name is not a plain identifier, is already used in the
    file as it was before (`original` chunks; Blockliner's own edit may already use the new name), or the text does not
    tokenize. Returns (chunks, [skipped descriptions])."""
    import keyword
    skipped = []
    for cid, (old, new) in renames.items():
        if not (new.isidentifier() and not keyword.iskeyword(new)):
            skipped.append(f"{new!r} is not a valid name")
            continue
        whole = "".join(t for _c, t in (original or chunks))
        used = _python_names(whole)
        if used is None:
            skipped.append(f"{old}: the file does not tokenize")
            continue
        if any(n == new for _l, _c, n, *_r in used):
            skipped.append(f"{new!r} is already used in the file")
            continue
        out = []
        for c, t in chunks:
            t2, _n = rename_python(t, old, new)
            out.append((c, t if t2 is None else t2))
        chunks = out
    return chunks, skipped


def join(chunks):
    return "".join(text for _cid, text in chunks)


def write_source(path, text, source):
    """Write `text` (with "\\n" line ends) back with the eol/bom the file had, atomically.
    Returns (size, mtime_ns, hash) of what is on disk now."""
    data = encode(text, source.eol, source.bom)
    safe_write.write_text_atomic(path, data)
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns, hash_file(path)
